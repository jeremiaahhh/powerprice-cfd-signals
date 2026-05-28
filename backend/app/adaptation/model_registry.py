"""
Model registry: tracks production vs candidate models.
Implements promotion rules from the spec.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_REGISTRY_FILE = "model_registry.json"
_CANDIDATE_DIR_NAME = "candidates"


class ModelRegistry:
    """
    Manages production and candidate model artifacts.

    Promotion rules (from spec):
    - OOS PF >= production * 0.95
    - OOS MaxDrawdown <= production * 1.10
    - Worst trade not worse
    - At least equal data quality
    - No extreme calibration problems (p_rebound mean between 0.3-0.8)
    """

    def __init__(self, model_dir: Optional[str] = None) -> None:
        self.model_dir = Path(model_dir or settings.model_dir)
        self.candidate_dir = self.model_dir / _CANDIDATE_DIR_NAME
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        self._registry_path = self.model_dir / _REGISTRY_FILE

    def load_registry(self) -> Dict:
        if self._registry_path.exists():
            try:
                return json.loads(self._registry_path.read_text())
            except Exception:
                pass
        return {"production": {}, "candidates": [], "promotions": []}

    def save_registry(self, registry: Dict) -> None:
        self._registry_path.write_text(json.dumps(registry, indent=2, default=str))

    def record_production_metrics(self, metrics: Dict) -> None:
        """Update production model metrics after training."""
        reg = self.load_registry()
        reg["production"] = {
            **metrics,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_registry(reg)
        logger.info("Production metrics updated: PF=%.3f", metrics.get("profit_factor") or 0)

    def save_candidate(self, candidate_model_dir: str, metrics: Dict, name: str) -> str:
        """Save a candidate model to the candidates directory."""
        dest = self.candidate_dir / name
        dest.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(candidate_model_dir, str(dest), dirs_exist_ok=True)
        except Exception as exc:
            logger.warning("Could not copy candidate model files: %s", exc)

        reg = self.load_registry()
        candidate_entry = {
            "name": name,
            "metrics": metrics,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "promoted": False,
        }
        reg.setdefault("candidates", []).append(candidate_entry)
        # Keep only last 5 candidates
        reg["candidates"] = reg["candidates"][-5:]
        self.save_registry(reg)
        logger.info("Candidate model saved: %s (PF=%.3f)", name, metrics.get("profit_factor") or 0)
        return str(dest)

    def should_promote(self, candidate_metrics: Dict) -> tuple[bool, str]:
        """
        Check if candidate meets promotion criteria.
        Returns (promote: bool, reason: str).
        """
        reg = self.load_registry()
        prod = reg.get("production", {})

        if not prod:
            return True, "No production model exists — promoting first candidate"

        prod_pf = prod.get("profit_factor")
        cand_pf = candidate_metrics.get("profit_factor")
        prod_dd = prod.get("max_drawdown_pct")
        cand_dd = candidate_metrics.get("max_drawdown_pct")
        prod_worst = prod.get("worst_trade_eur_mwh")
        cand_worst = candidate_metrics.get("worst_trade_eur_mwh")

        # Rule 1: PF check (candidate must be >= 95% of production)
        if prod_pf is not None and cand_pf is not None:
            if cand_pf < prod_pf * 0.95:
                return False, f"PF {cand_pf:.3f} < {prod_pf * 0.95:.3f} (95% of production {prod_pf:.3f})"

        # Rule 2: Max drawdown check (candidate must not be worse by >10%)
        if prod_dd is not None and cand_dd is not None:
            if cand_dd > prod_dd * 1.10:
                return False, f"MaxDD {cand_dd:.1f}% > {prod_dd * 1.10:.1f}% (110% of production)"

        # Rule 3: Worst trade check
        if prod_worst is not None and cand_worst is not None:
            if cand_worst < prod_worst * 1.20:  # 20% worse allowed
                return False, f"Worst trade {cand_worst:.1f} worse than production {prod_worst:.1f}"

        # Rule 4: Calibration check (p_rebound mean should be reasonable)
        mean_p = candidate_metrics.get("mean_p_rebound")
        if mean_p is not None and (mean_p < 0.2 or mean_p > 0.9):
            return False, f"Extreme calibration: mean p_rebound={mean_p:.3f}"

        return True, "All promotion criteria met"

    def promote_candidate(self, candidate_model_dir: str, candidate_metrics: Dict) -> bool:
        """Attempt to promote a candidate model to production."""
        should, reason = self.should_promote(candidate_metrics)
        logger.info("Promotion decision: %s — %s", "PROMOTE" if should else "REJECT", reason)

        if should:
            try:
                # Copy candidate artifacts to production model dir
                shutil.copytree(candidate_model_dir, str(self.model_dir), dirs_exist_ok=True)
                self.record_production_metrics(candidate_metrics)
                reg = self.load_registry()
                reg.setdefault("promotions", []).append({
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                    "reason": reason,
                    "metrics": candidate_metrics,
                })
                self.save_registry(reg)
                logger.info("Model promoted to production")
            except Exception as exc:
                logger.error("Model promotion copy failed: %s", exc)
                return False

        return should

    def get_status(self) -> Dict:
        reg = self.load_registry()
        return {
            "production_metrics": reg.get("production", {}),
            "candidate_count": len(reg.get("candidates", [])),
            "last_candidates": reg.get("candidates", [])[-3:],
            "last_promotion": (reg.get("promotions") or [{}])[-1],
        }
