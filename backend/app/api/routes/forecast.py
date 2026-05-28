"""
Forecast routes.

GET /forecast            – full multi-model forecast for the current hour
GET /forecast/negative   – p_negative for the next 6 hours
GET /forecast/rebound    – p_rebound and expected rebound magnitude
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.db.models import HourlyPrice
from app.api.schemas import ForecastResponse, HourlyForecastPoint

logger = get_logger(__name__)
router = APIRouter()

_MODEL_NOT_TRAINED_MSG = "Models have not been trained yet. Run /backtest/run or trigger model training first."


# ---------------------------------------------------------------------------
# Lazy model loaders with module-level cache (load once per process)
# ---------------------------------------------------------------------------

_neg_clf_cache = None
_reb_clf_cache = None
_price_model_cache = None
_model_load_attempted = {"neg": False, "reb": False, "price": False}


def _load_negative_classifier():
    global _neg_clf_cache
    if _model_load_attempted["neg"]:
        return _neg_clf_cache
    _model_load_attempted["neg"] = True
    try:
        from app.ml.negative_price_classifier import NegativePriceClassifier
        clf = NegativePriceClassifier(model_dir=settings.model_dir)
        clf.load()
        _neg_clf_cache = clf
        return clf
    except Exception as exc:
        logger.warning("NegativePriceClassifier not available: %s", exc)
        return None


def _load_rebound_classifier():
    global _reb_clf_cache
    if _model_load_attempted["reb"]:
        return _reb_clf_cache
    _model_load_attempted["reb"] = True
    try:
        from app.ml.rebound_classifier import ReboundClassifier
        clf = ReboundClassifier(model_dir=settings.model_dir)
        clf.load()
        _reb_clf_cache = clf
        return clf
    except Exception as exc:
        logger.warning("ReboundClassifier not available: %s", exc)
        return None


def _load_price_regression():
    global _price_model_cache
    if _model_load_attempted["price"]:
        return _price_model_cache
    _model_load_attempted["price"] = True
    try:
        from app.ml.price_regression import PriceRegressionModel
        model = PriceRegressionModel(model_dir=settings.model_dir)
        model.load()
        _price_model_cache = model
        return model
    except Exception as exc:
        logger.warning("PriceRegressionModel not available: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_recent_df(db: AsyncSession, hours: int = 72) -> pd.DataFrame:
    """Fetch recent HourlyPrice rows as a DataFrame for feature engineering."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(HourlyPrice)
        .where(HourlyPrice.timestamp >= cutoff)
        .order_by(HourlyPrice.timestamp.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        return pd.DataFrame()

    data = []
    for r in rows:
        data.append({
            "timestamp": r.timestamp,
            "price_eur_mwh": r.price_eur_mwh,
            "load_mw": r.load_mw,
            "wind_onshore_mw": r.wind_onshore_mw,
            "wind_offshore_mw": r.wind_offshore_mw,
            "solar_mw": r.solar_mw,
            "residual_load_mw": r.residual_load_mw,
            "net_export_mw": r.net_export_mw,
            "temperature_c": r.temperature_c,
            "wind_speed_ms": r.wind_speed_ms,
            "solar_radiation_wm2": r.solar_radiation_wm2,
            "cloud_cover_pct": r.cloud_cover_pct,
            "is_holiday": int(r.is_holiday) if r.is_holiday is not None else 0,
            "is_weekend": int(r.is_weekend) if r.is_weekend is not None else 0,
            "hour": r.hour,
            "month": r.month,
        })

    return pd.DataFrame(data)


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Run feature engineering and return the feature matrix for the latest row."""
    try:
        from app.features.engineering import FeatureEngineer
        fe = FeatureEngineer()
        features_df = fe.build_features(df)
        return features_df
    except Exception as exc:
        logger.error("Feature engineering failed: %s", exc)
        return pd.DataFrame()


def _predict_safe(model, X: pd.DataFrame, method: str = "predict_proba") -> Optional[float]:
    """Run a model prediction and return a scalar, or None on failure."""
    if model is None or X is None or X.empty:
        return None
    try:
        if method == "predict_proba":
            proba = model.predict_proba(X)
            if proba is not None and len(proba) > 0:
                # Return probability of positive class
                arr = np.array(proba)
                if arr.ndim == 2:
                    return float(arr[-1, 1])
                return float(arr[-1])
        elif method == "predict":
            pred = model.predict(X)
            if pred is not None and len(pred) > 0:
                return float(np.array(pred)[-1])
    except Exception as exc:
        logger.warning("Model prediction failed (%s): %s", method, exc)
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ForecastResponse, summary="Full multi-model forecast")
async def get_forecast(db: AsyncSession = Depends(get_db)) -> ForecastResponse:
    """
    Return the current forecast from all trained ML models.

    Loads the latest features from the database, runs the NegativePriceClassifier,
    ReboundClassifier, and PriceRegressionModel, and returns a structured forecast.
    """
    now = datetime.now(timezone.utc)

    # Fetch recent data for feature engineering
    df = await _fetch_recent_df(db, hours=72)

    if df.empty:
        raise HTTPException(
            status_code=503,
            detail="No market data available. Run /data/ingest first.",
        )

    # Build feature matrix
    features_df = _build_features(df)

    if features_df.empty:
        raise HTTPException(
            status_code=503,
            detail="Feature engineering produced no rows. Insufficient historical data.",
        )

    # Get the feature matrix (last row = current hour)
    from app.features.engineering import FeatureEngineer
    fe = FeatureEngineer()
    available_cols = [c for c in fe.FEATURE_COLUMNS if c in features_df.columns]

    # Get rows that have no NaNs across feature columns
    valid_mask = features_df[available_cols].notna().all(axis=1)
    valid_features = features_df.loc[valid_mask, available_cols]

    if valid_features.empty:
        raise HTTPException(
            status_code=503,
            detail=_MODEL_NOT_TRAINED_MSG,
        )

    X_latest = valid_features.tail(1)

    # Latest known price
    latest_price: Optional[float] = None
    latest_ts: Optional[datetime] = None
    if "price_eur_mwh" in df.columns and df["price_eur_mwh"].notna().any():
        latest_price = float(df["price_eur_mwh"].dropna().iloc[-1])
    if "timestamp" in df.columns:
        ts_raw = df["timestamp"].iloc[-1]
        if hasattr(ts_raw, "tzinfo"):
            latest_ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        else:
            latest_ts = now

    latest_ts = latest_ts or now

    # Load and run models
    neg_clf = _load_negative_classifier()
    reb_clf = _load_rebound_classifier()
    price_model = _load_price_regression()

    p_negative = _predict_safe(neg_clf, X_latest, "predict_proba")
    p_rebound = _predict_safe(reb_clf, X_latest, "predict_proba")
    predicted_price = _predict_safe(price_model, X_latest, "predict")

    models_available = any(m is not None for m in [neg_clf, reb_clf, price_model])

    if not models_available:
        raise HTTPException(
            status_code=503,
            detail=_MODEL_NOT_TRAINED_MSG,
        )

    # Build forecast points for the next 6 hours
    horizon_hours = 6
    forecast_points: List[HourlyForecastPoint] = []

    for h in range(1, horizon_hours + 1):
        ts_h = latest_ts + timedelta(hours=h)
        # Use model output for hour 1; decay confidence for further horizons
        decay = max(0.0, 1.0 - (h - 1) * 0.1)
        p_neg_h = (p_negative * decay) if p_negative is not None else None
        p_reb_h = (p_rebound * decay) if p_rebound is not None else None
        pred_price_h = predicted_price if h == 1 else (
            predicted_price * (1 + (h - 1) * 0.02) if predicted_price is not None else None
        )
        forecast_points.append(
            HourlyForecastPoint(
                timestamp=ts_h,
                predicted_price_eur_mwh=pred_price_h if pred_price_h is not None else (latest_price or 0.0),
                p_negative=min(1.0, p_neg_h) if p_neg_h is not None else None,
                p_rebound=min(1.0, p_reb_h) if p_reb_h is not None else None,
            )
        )

    # Determine model info
    model_names = []
    if neg_clf is not None:
        model_names.append("NegativePriceClassifier")
    if reb_clf is not None:
        model_names.append("ReboundClassifier")
    if price_model is not None:
        model_names.append("PriceRegressionModel")

    model_name = "+".join(model_names) if model_names else "unavailable"

    # Feature importance (from price regression model if available)
    feature_importance: Optional[Dict[str, float]] = None
    if price_model is not None:
        try:
            fi = getattr(price_model, "feature_importances_", None)
            if fi is None and hasattr(price_model, "model"):
                fi = getattr(price_model.model, "feature_importances_", None)
            if fi is not None and len(fi) == len(available_cols):
                feature_importance = {
                    col: round(float(val), 4)
                    for col, val in zip(available_cols, fi)
                }
        except Exception:
            pass

    return ForecastResponse(
        generated_at=now,
        model_name=model_name,
        model_version=None,
        horizon_hours=horizon_hours,
        forecast=forecast_points,
        feature_importance=feature_importance,
    )


@router.get("/negative", summary="P(negative price) for next 6 hours")
async def get_negative_forecast(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Return the probability that the electricity price will be negative
    for each of the next 6 hours.
    """
    now = datetime.now(timezone.utc)
    df = await _fetch_recent_df(db, hours=72)

    if df.empty:
        raise HTTPException(status_code=503, detail="No market data available.")

    features_df = _build_features(df)

    from app.features.engineering import FeatureEngineer
    fe = FeatureEngineer()
    available_cols = [c for c in fe.FEATURE_COLUMNS if c in features_df.columns]
    valid_mask = features_df[available_cols].notna().all(axis=1)
    valid_features = features_df.loc[valid_mask, available_cols]

    neg_clf = _load_negative_classifier()

    if neg_clf is None:
        return {
            "status": "unavailable",
            "message": _MODEL_NOT_TRAINED_MSG,
            "generated_at": now.isoformat(),
        }

    p_negative_now = _predict_safe(neg_clf, valid_features.tail(1), "predict_proba")

    latest_price: Optional[float] = None
    if "price_eur_mwh" in df.columns and df["price_eur_mwh"].notna().any():
        latest_price = float(df["price_eur_mwh"].dropna().iloc[-1])

    hourly_forecasts = []
    for h in range(1, 7):
        ts_h = now + timedelta(hours=h)
        decay = max(0.0, 1.0 - (h - 1) * 0.1)
        p_neg_h = (p_negative_now * decay) if p_negative_now is not None else None
        hourly_forecasts.append({
            "timestamp": ts_h.isoformat(),
            "hour_offset": h,
            "p_negative": round(p_neg_h, 4) if p_neg_h is not None else None,
        })

    return {
        "generated_at": now.isoformat(),
        "current_price_eur_mwh": latest_price,
        "p_negative_current_hour": round(p_negative_now, 4) if p_negative_now is not None else None,
        "hourly_forecast": hourly_forecasts,
        "model": "NegativePriceClassifier",
    }


@router.get("/rebound", summary="P(rebound) and expected rebound magnitude")
async def get_rebound_forecast(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Return the probability of a price rebound within the forecast horizon
    and an estimate of the expected rebound magnitude.
    """
    now = datetime.now(timezone.utc)
    df = await _fetch_recent_df(db, hours=72)

    if df.empty:
        raise HTTPException(status_code=503, detail="No market data available.")

    features_df = _build_features(df)

    from app.features.engineering import FeatureEngineer
    fe = FeatureEngineer()
    available_cols = [c for c in fe.FEATURE_COLUMNS if c in features_df.columns]
    valid_mask = features_df[available_cols].notna().all(axis=1)
    valid_features = features_df.loc[valid_mask, available_cols]

    reb_clf = _load_rebound_classifier()
    price_model = _load_price_regression()

    if reb_clf is None and price_model is None:
        return {
            "status": "unavailable",
            "message": _MODEL_NOT_TRAINED_MSG,
            "generated_at": now.isoformat(),
        }

    latest_price: Optional[float] = None
    if "price_eur_mwh" in df.columns and df["price_eur_mwh"].notna().any():
        latest_price = float(df["price_eur_mwh"].dropna().iloc[-1])

    p_rebound = _predict_safe(reb_clf, valid_features.tail(1), "predict_proba")
    predicted_price = _predict_safe(price_model, valid_features.tail(1), "predict")

    expected_rebound: Optional[float] = None
    if predicted_price is not None and latest_price is not None:
        expected_rebound = round(predicted_price - latest_price, 2)

    return {
        "generated_at": now.isoformat(),
        "current_price_eur_mwh": latest_price,
        "p_rebound": round(p_rebound, 4) if p_rebound is not None else None,
        "predicted_price_eur_mwh": round(predicted_price, 2) if predicted_price is not None else None,
        "expected_rebound_eur_mwh": expected_rebound,
        "forecast_horizon_hours": 6,
        "models": {
            "rebound_classifier": reb_clf is not None,
            "price_regression": price_model is not None,
        },
    }
