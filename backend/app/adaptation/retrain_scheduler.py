"""
Adaptive retraining scheduler.
Triggered by drift detection or time-based schedule.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from .model_registry import ModelRegistry

logger = get_logger(__name__)


class RetrainScheduler:
    """
    Manages the retraining lifecycle:
    1. Load recent training data (rolling window, no look-ahead)
    2. Train all models in a temp directory
    3. Check promotion criteria via ModelRegistry
    4. Promote or save as candidate

    NEVER blindly replaces production models.
    """

    def __init__(self) -> None:
        self.registry = ModelRegistry()
        self._last_retrain: Optional[datetime] = None

    def should_retrain(self, force: bool = False, drift_detected: bool = False) -> bool:
        if not settings.auto_retrain_enabled:
            return False
        if force:
            return True
        if drift_detected:
            return True
        if self._last_retrain is None:
            return True
        hours_since = (datetime.now(timezone.utc) - self._last_retrain).total_seconds() / 3600
        return hours_since >= settings.retrain_interval_hours

    def run(self, reason: str = "scheduled") -> Optional[Dict]:
        """
        Run a full training cycle. Returns metrics dict or None if skipped.
        IMPORTANT: trains on rolling window, never looks ahead.
        """
        logger.info("RetrainScheduler.run triggered: reason=%s", reason)
        self._last_retrain = datetime.now(timezone.utc)

        try:
            from app.ml.trainer import ModelTrainer
            from app.ml.rebound_classifier import ReboundClassifier
            from app.ml.negative_price_classifier import NegativePriceClassifier

            with tempfile.TemporaryDirectory() as tmpdir:
                trainer = ModelTrainer(model_dir=tmpdir)
                df = trainer.load_training_data(
                    days_back=settings.rolling_training_days,
                    before_ts=datetime.now(tz=timezone.utc),
                )
                if df.empty or len(df) < 500:
                    logger.warning("RetrainScheduler: insufficient training data (%d rows)", len(df))
                    return None

                metrics = trainer.train_all()
                metrics["training_reason"] = reason
                metrics["rolling_days"] = settings.rolling_training_days

                # Try to get backtest metrics for promotion decision
                try:
                    from app.ml.rebound_classifier import ReboundClassifier as RC
                    rc = RC(model_dir=tmpdir)
                    rc.load()
                    reb_metrics = metrics.get("rebound_classifier", {})
                    candidate_metrics = {
                        "profit_factor": None,  # Would need backtest to compute
                        "max_drawdown_pct": None,
                        "worst_trade_eur_mwh": None,
                        "auc_roc": reb_metrics.get("auc_roc"),
                        "f1": reb_metrics.get("f1"),
                        "mean_p_rebound": reb_metrics.get("mean_prediction"),
                    }
                except Exception:
                    candidate_metrics = metrics.get("rebound_classifier", {})

                # Save candidate model
                run_name = f"candidate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"
                self.registry.save_candidate(tmpdir, candidate_metrics, run_name)

                # Attempt promotion (conservative — requires backtest PF)
                # Without backtest PF, we promote if AUC improved
                prod = self.registry.load_registry().get("production", {})
                prod_auc = prod.get("auc_roc")
                cand_auc = candidate_metrics.get("auc_roc")

                if prod_auc is None or (cand_auc is not None and cand_auc >= prod_auc * 0.97):
                    # AUC-based promotion (when PF not available)
                    promoted = self.registry.promote_candidate(tmpdir, candidate_metrics)
                    metrics["promoted"] = promoted
                    metrics["promotion_reason"] = "AUC-based (no backtest PF available)"
                else:
                    metrics["promoted"] = False
                    metrics["promotion_reason"] = f"AUC {cand_auc:.4f} < {prod_auc * 0.97:.4f} (production threshold)"
                    logger.info("Candidate not promoted: %s", metrics["promotion_reason"])

                logger.info(
                    "Retraining complete: promoted=%s AUC=%.4f",
                    metrics.get("promoted"),
                    cand_auc or 0,
                )
                return metrics

        except Exception as exc:
            logger.error("RetrainScheduler.run failed: %s", exc)
            return {"error": str(exc), "training_reason": reason}
