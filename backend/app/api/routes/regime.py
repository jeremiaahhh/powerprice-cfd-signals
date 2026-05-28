from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.db.models import HourlyPrice

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rows_to_df(rows: list) -> pd.DataFrame:
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/current", summary="Classify current market regime")
async def get_current_regime(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=72)

    try:
        stmt = (
            select(HourlyPrice)
            .where(
                HourlyPrice.timestamp >= cutoff,
                HourlyPrice.price_eur_mwh.isnot(None),
            )
            .order_by(HourlyPrice.timestamp.asc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise HTTPException(
                status_code=503,
                detail="No market data available for the last 72h — run /data/ingest first",
            )

        df = _rows_to_df(rows)

        from app.features.engineering import FeatureEngineer
        fe = FeatureEngineer()
        features_df = fe.build_features(df)

        available_cols = [c for c in fe.FEATURE_COLUMNS if c in features_df.columns]
        valid_mask = features_df[available_cols].notna().all(axis=1)
        valid_rows = features_df[valid_mask]

        if valid_rows.empty:
            raise HTTPException(
                status_code=503,
                detail="Insufficient feature data — not enough history to classify regime",
            )

        feature_row = valid_rows.iloc[-1]  # Series

        from app.regime import RegimeClassifier
        classifier = RegimeClassifier()
        regime_result = classifier.classify(feature_row)

        # Pull readable market context from the last raw row
        last_raw = df.iloc[-1]

        wind_total = (
            (last_raw.get("wind_onshore_mw") or 0.0)
            + (last_raw.get("wind_offshore_mw") or 0.0)
        )
        solar = last_raw.get("solar_mw")
        load = last_raw.get("load_mw")
        renewable_share: Optional[float] = None
        if load and load > 0 and solar is not None:
            renewable_share = round((wind_total + (solar or 0.0)) / load * 100.0, 2)

        prices_24h = df["price_eur_mwh"].dropna().tail(24)
        price_vol_24h = round(float(prices_24h.std()), 2) if len(prices_24h) >= 2 else None
        hours_negative_24h = int((prices_24h < 0).sum())

        oversupply_index: Optional[float] = None
        residual = last_raw.get("residual_load_mw")
        if residual is not None and load and load > 0:
            oversupply_index = round(1.0 - residual / load, 4)

        response: Dict[str, Any] = {
            "regime": regime_result.regime.value if hasattr(regime_result.regime, "value") else str(regime_result.regime),
            "confidence": round(regime_result.confidence, 4) if regime_result.confidence is not None else None,
            "renewable_share": renewable_share,
            "price_volatility_24h": price_vol_24h,
            "hours_negative_24h": hours_negative_24h,
            "solar_mw": solar,
            "wind_mw": round(wind_total, 1),
            "oversupply_index": oversupply_index,
            "description": getattr(regime_result, "description", None),
            "signal_thresholds": getattr(regime_result, "signal_thresholds", None),
            "generated_at": now.isoformat(),
        }
        logger.info("GET /regime/current: classified as %s (conf=%.2f)", response["regime"], response["confidence"] or 0)
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GET /regime/current failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Regime classification failed: {exc}")


@router.get("/history", summary="Last N regime snapshots")
async def get_regime_history(
    limit: int = Query(default=48, ge=1, le=720, description="Number of snapshots to return"),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    try:
        from app.db.models import RegimeSnapshot
    except ImportError:
        logger.warning("RegimeSnapshot model not found — returning empty list")
        return []

    try:
        stmt = (
            select(RegimeSnapshot)
            .order_by(RegimeSnapshot.timestamp.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        snapshots = []
        for row in rows:
            snapshots.append({
                k: v for k, v in row.__dict__.items()
                if not k.startswith("_")
            })

        logger.info("GET /regime/history: returning %d snapshots", len(snapshots))
        return snapshots

    except Exception as exc:
        logger.exception("GET /regime/history failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Failed to fetch regime history: {exc}")
