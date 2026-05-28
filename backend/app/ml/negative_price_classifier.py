"""
XGBoost-based binary classifier for negative electricity price prediction.

Predicts the probability that the spot price will be < 0 EUR/MWh within
the next ``horizon_hours`` hours.  Walk-forward (TimeSeriesSplit)
cross-validation is used to avoid look-ahead bias.
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
)
from xgboost import XGBClassifier

from app.core.config import settings
from app.core.logging import get_logger
from app.features.engineering import FeatureEngineer

logger = get_logger(__name__)

_MODEL_FILE = "negative_price_classifier.joblib"
_SCALER_FILE = "negative_price_scaler.joblib"
_META_FILE = "negative_price_meta.json"


class NegativePriceClassifier:
    """Predicts probability that electricity price will be < 0 EUR/MWh.

    The model operates on the feature set defined by
    :class:`~app.features.engineering.FeatureEngineer`.  A ``StandardScaler``
    is fitted on the training split and applied consistently at inference time
    (XGBoost does not require scaling, but it improves interpretability of
    feature-importance values when compared to linear baselines).

    Parameters
    ----------
    model_dir:
        Directory where model artefacts are persisted.
    horizon_hours:
        Future look-ahead used when constructing the target variable.
        The label is 1 if the **minimum** price in the next
        ``horizon_hours`` is negative.
    """

    def __init__(self, model_dir: str, horizon_hours: int = 4) -> None:
        self.model_dir = model_dir
        self.horizon_hours = horizon_hours

        self.model: Optional[XGBClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names: Optional[List[str]] = None
        self.metrics: Dict = {}

        self._fe = FeatureEngineer()

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, df: pd.DataFrame) -> Dict:
        """Train the classifier with walk-forward cross-validation.

        Parameters
        ----------
        df:
            Raw HourlyPrice DataFrame sorted by timestamp.

        Returns
        -------
        dict
            Keys: ``accuracy``, ``auc_roc``, ``precision``, ``recall``,
            ``f1``, ``n_train``, ``n_positive``, ``class_balance``,
            ``n_folds``, ``training_time_s``.
        """
        t0 = time.perf_counter()
        logger.info("Training NegativePriceClassifier (horizon=%dh)", self.horizon_hours)

        X, _ = self._fe.get_feature_matrix(df)
        y = self._build_target(df, X.index)

        if len(X) == 0:
            raise ValueError("No usable training rows after feature engineering.")

        self.feature_names = list(X.columns)
        n_pos = int(y.sum())
        n_total = len(y)
        n_neg = n_total - n_pos
        class_balance = n_pos / n_total if n_total > 0 else 0.0

        logger.info(
            "Dataset: %d rows, %d positive (%.1f%%), %d negative",
            n_total, n_pos, class_balance * 100, n_neg,
        )

        # scale_pos_weight compensates for class imbalance
        spw = n_neg / n_pos if n_pos > 0 else 1.0

        xgb_params = dict(
            n_estimators=400,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            gamma=1.0,
            reg_alpha=0.1,
            reg_lambda=1.0,
            scale_pos_weight=spw,
            objective="binary:logistic",
            eval_metric="auc",
            use_label_encoder=False,
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
        )

        # ---- Walk-forward cross-validation ---------------------------
        tscv = TimeSeriesSplit(n_splits=5)
        fold_metrics: List[Dict] = []

        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

            if y_val.sum() == 0:
                logger.warning("Fold %d has no positive examples – skipping.", fold_idx)
                continue

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_val_s = scaler.transform(X_val)

            model = XGBClassifier(**xgb_params)
            model.fit(
                X_tr_s, y_tr,
                eval_set=[(X_val_s, y_val)],
                verbose=False,
            )

            y_pred = model.predict(X_val_s)
            y_proba = model.predict_proba(X_val_s)[:, 1]

            fold_metrics.append({
                "accuracy": accuracy_score(y_val, y_pred),
                "auc_roc": roc_auc_score(y_val, y_proba),
                "precision": precision_score(y_val, y_pred, zero_division=0),
                "recall": recall_score(y_val, y_pred, zero_division=0),
                "f1": f1_score(y_val, y_pred, zero_division=0),
            })
            logger.debug(
                "Fold %d: AUC=%.4f F1=%.4f", fold_idx,
                fold_metrics[-1]["auc_roc"], fold_metrics[-1]["f1"],
            )

        if not fold_metrics:
            raise ValueError("All CV folds were skipped (no positive examples).")

        avg_metrics = {
            k: float(np.mean([m[k] for m in fold_metrics]))
            for k in fold_metrics[0]
        }

        # ---- Final model on full data --------------------------------
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        self.model = XGBClassifier(**xgb_params)
        self.model.fit(X_scaled, y, verbose=False)

        elapsed = time.perf_counter() - t0
        self.metrics = {
            **avg_metrics,
            "n_train": n_total,
            "n_positive": n_pos,
            "class_balance": round(class_balance, 4),
            "n_folds": len(fold_metrics),
            "training_time_s": round(elapsed, 2),
        }

        logger.info(
            "NegativePriceClassifier trained: AUC=%.4f F1=%.4f (%.1fs)",
            self.metrics["auc_roc"], self.metrics["f1"], elapsed,
        )
        return self.metrics

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict_proba(self, features: pd.DataFrame) -> float:
        """Return probability of negative price (scalar 0 – 1).

        Parameters
        ----------
        features:
            DataFrame with the same columns as produced by
            :meth:`FeatureEngineer.build_features`.  Typically a single
            row representing the *current* hour.

        Returns
        -------
        float
            Probability in [0, 1].
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("Model not loaded. Call load() or train() first.")

        X = self._align_features(features)
        X_s = self.scaler.transform(X)
        prob = float(self.model.predict_proba(X_s)[0, 1])
        return prob

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> str:
        """Persist model, scaler, and metadata to ``model_dir``.

        Returns
        -------
        str
            Absolute path to the model file.
        """
        if self.model is None:
            raise RuntimeError("No trained model to save.")

        Path(self.model_dir).mkdir(parents=True, exist_ok=True)
        model_path = os.path.join(self.model_dir, _MODEL_FILE)
        scaler_path = os.path.join(self.model_dir, _SCALER_FILE)
        meta_path = os.path.join(self.model_dir, _META_FILE)

        joblib.dump(self.model, model_path)
        joblib.dump(self.scaler, scaler_path)

        meta = {
            "horizon_hours": self.horizon_hours,
            "feature_names": self.feature_names,
            "metrics": self.metrics,
            "saved_at": pd.Timestamp.utcnow().isoformat(),
        }
        with open(meta_path, "w") as fh:
            json.dump(meta, fh, indent=2)

        logger.info("NegativePriceClassifier saved to %s", model_path)
        return model_path

    def load(self) -> None:
        """Load model artefacts from ``model_dir``."""
        model_path = os.path.join(self.model_dir, _MODEL_FILE)
        scaler_path = os.path.join(self.model_dir, _SCALER_FILE)
        meta_path = os.path.join(self.model_dir, _META_FILE)

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)

        if os.path.exists(meta_path):
            with open(meta_path) as fh:
                meta = json.load(fh)
            self.feature_names = meta.get("feature_names")
            self.metrics = meta.get("metrics", {})
            # Restore horizon from metadata so registry can interrogate it
            saved_horizon = meta.get("horizon_hours")
            if saved_horizon is not None:
                self.horizon_hours = saved_horizon

        logger.info("NegativePriceClassifier loaded from %s", model_path)

    # ------------------------------------------------------------------
    # Interpretability
    # ------------------------------------------------------------------

    def get_feature_importance(self) -> Dict[str, float]:
        """Return ``{feature_name: importance_score}`` sorted descending.

        Uses XGBoost's ``weight``-based importance (number of splits on
        each feature).  Callers can request ``gain`` or ``cover`` via the
        underlying model directly.
        """
        if self.model is None:
            raise RuntimeError("Model not loaded.")

        scores = self.model.get_booster().get_fscore()
        names = self.feature_names or list(scores.keys())
        # get_fscore returns keys like 'f0', 'f1' when feature names are not
        # set on the booster; map back to names if available.
        if all(k.startswith("f") and k[1:].isdigit() for k in scores):
            importance = {
                names[int(k[1:])]: float(v)
                for k, v in scores.items()
                if int(k[1:]) < len(names)
            }
        else:
            importance = {k: float(v) for k, v in scores.items()}

        return dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_target(self, df: pd.DataFrame, valid_index: pd.Index) -> pd.Series:
        """Build the forward-looking negative-price label.

        Label at row *i* is 1 if the minimum price in ``[i+1, i+horizon_hours]``
        is < 0.  This predicts whether a negative-price *period* starts within
        the horizon, not just the current hour.
        """
        df_sorted = df.sort_values("timestamp").reset_index(drop=True)
        price = df_sorted["price_eur_mwh"].values
        n = len(price)
        labels = np.zeros(n, dtype=int)

        for i in range(n):
            end = min(i + self.horizon_hours + 1, n)
            future = price[i + 1 : end]
            if len(future) > 0 and np.nanmin(future) < 0:
                labels[i] = 1

        label_series = pd.Series(labels, name="target")
        # Re-index to match the valid (NaN-dropped) rows from get_feature_matrix
        # We know df_sorted index == 0..n-1 and valid_index is a subset.
        label_series = label_series.loc[valid_index]
        return label_series.reset_index(drop=True)

    def _align_features(self, features: pd.DataFrame) -> pd.DataFrame:
        """Select and order columns to match training feature set."""
        if self.feature_names is None:
            raise RuntimeError("feature_names not set; model may not be trained.")

        # Add missing columns as 0.0, drop extras
        for col in self.feature_names:
            if col not in features.columns:
                features = features.copy()
                features[col] = 0.0

        return features[self.feature_names].fillna(0.0)
