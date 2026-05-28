"""
Battery storage intelligence API endpoints.

GET /battery/latest         – Latest battery state (capacity + proxy)
GET /battery/capacity       – Installed capacity overview
GET /battery/flows          – Recent charge/discharge flow history
GET /battery/proxy          – Raw proxy feature table for recent hours
GET /battery/features       – Current battery features for signal engine
GET /battery/regime-impact  – Battery state vs current regime thresholds
GET /battery/data-quality   – Data source quality and availability report
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.db.models import HourlyPrice
from app.services.battery_service import BatteryService

logger = get_logger(__name__)
router = APIRouter()

_svc = BatteryService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_price_df(db: AsyncSession, hours: int = 72) -> pd.DataFrame:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(HourlyPrice)
        .where(HourlyPrice.timestamp >= cutoff, HourlyPrice.price_eur_mwh.isnot(None))
        .order_by(HourlyPrice.timestamp.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        def sf(v):
            try:
                return float(v) if v is not None else None
            except Exception:
                return None
        data.append({
            "timestamp":            r.timestamp,
            "price_eur_mwh":        sf(r.price_eur_mwh),
            "load_mw":              sf(r.load_mw),
            "wind_onshore_mw":      sf(r.wind_onshore_mw),
            "wind_offshore_mw":     sf(r.wind_offshore_mw),
            "solar_mw":             sf(r.solar_mw),
            "residual_load_mw":     sf(r.residual_load_mw),
            "net_export_mw":        sf(getattr(r, "net_export_mw", None)),
            "temperature_c":        sf(r.temperature_c),
            "wind_speed_ms":        sf(r.wind_speed_ms),
            "solar_radiation_wm2":  sf(r.solar_radiation_wm2),
            "cloud_cover_pct":      sf(r.cloud_cover_pct),
            "battery_net_mw":       sf(getattr(r, "battery_net_mw", None)),
            "is_holiday":           int(r.is_holiday) if r.is_holiday is not None else 0,
            "is_weekend":           int(r.is_weekend) if r.is_weekend is not None else 0,
            "hour":                 r.hour,
            "month":                r.month,
        })
    return pd.DataFrame(data)


def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert DataFrame to JSON-serializable list of dicts."""
    df = df.copy()
    for col in df.select_dtypes(include=["datetime64[ns, UTC]", "datetime64[ns]"]).columns:
        df[col] = df[col].astype(str)
    df["timestamp"] = df["timestamp"].astype(str) if "timestamp" in df.columns else None
    return df.where(df.notna(), other=None).to_dict(orient="records")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/latest", summary="Latest battery state")
async def get_battery_latest(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return the current installed capacity and latest proxy state."""
    try:
        capacity = await _svc.get_installed_capacity()
        df = await _fetch_price_df(db, hours=24)
        if df.empty:
            return {"capacity": capacity, "latest_proxy": None, "generated_at": datetime.now(timezone.utc).isoformat()}
        batt_df = await _svc.get_battery_features(df)
        latest = {}
        if not batt_df.empty:
            row = batt_df.iloc[-1]
            for col in ["battery_saturation_proxy", "storage_charge_pressure", "storage_discharge_pressure",
                        "net_battery_flow_mw", "battery_charging_mw", "battery_discharging_mw",
                        "pv_surplus_after_load", "midday_price_compression", "evening_arbitrage_spread"]:
                val = row.get(col)
                latest[col] = round(float(val), 4) if val is not None and str(val) != "nan" else None
            latest["timestamp"] = str(row.get("timestamp", ""))
        return {
            "capacity":      capacity,
            "latest_proxy":  latest,
            "generated_at":  datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.exception("GET /battery/latest failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/capacity", summary="Installed battery capacity")
async def get_battery_capacity() -> Dict[str, Any]:
    """Return installed capacity estimate with source metadata."""
    try:
        return await _svc.get_installed_capacity()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/flows", summary="Recent battery charge/discharge flows")
async def get_battery_flows(
    hours: int = Query(default=48, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return hourly battery flow estimates for the last N hours."""
    try:
        df = await _fetch_price_df(db, hours=hours)
        if df.empty:
            return []
        proxy_df = await _svc.get_proxy_features(df)
        flow_cols = ["timestamp", "charging_mw", "discharging_mw", "net_battery_flow_mw",
                     "source", "is_proxy", "data_quality_score"]
        available = [c for c in flow_cols if c in proxy_df.columns]
        return _df_to_records(proxy_df[available])
    except Exception as exc:
        logger.exception("GET /battery/flows failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/proxy", summary="Storage proxy feature table")
async def get_battery_proxy(
    hours: int = Query(default=48, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return raw proxy feature table (all proxy columns) for the last N hours."""
    try:
        df = await _fetch_price_df(db, hours=hours)
        if df.empty:
            return []
        proxy_df = await _svc.get_proxy_features(df)
        return _df_to_records(proxy_df)
    except Exception as exc:
        logger.exception("GET /battery/proxy failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/features", summary="Current battery features for signal engine")
async def get_battery_features(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return battery features computed for the latest hour."""
    try:
        df = await _fetch_price_df(db, hours=72)
        if df.empty:
            raise HTTPException(status_code=503, detail="No market data available")
        batt_df = await _svc.get_battery_features(df)
        if batt_df.empty:
            return {"status": "no_data"}
        row = batt_df.iloc[-1]
        from app.features.battery_features import BATTERY_FEATURE_COLUMNS
        features = {}
        for col in BATTERY_FEATURE_COLUMNS:
            val = row.get(col)
            features[col] = round(float(val), 4) if val is not None and str(val) != "nan" else None
        return {
            "status":       "ok",
            "timestamp":    str(row.get("timestamp", "")),
            "features":     features,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GET /battery/features failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/regime-impact", summary="Battery impact on current regime and signal thresholds")
async def get_battery_regime_impact(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Show how battery state interacts with current regime thresholds."""
    try:
        df = await _fetch_price_df(db, hours=72)
        if df.empty:
            raise HTTPException(status_code=503, detail="No market data")

        batt_df = await _svc.get_battery_features(df)

        # Get current regime
        from app.features.engineering import FeatureEngineer
        from app.regime import RegimeClassifier
        fe = FeatureEngineer()
        feat_df = fe.build_features(df)
        available = [c for c in fe.FEATURE_COLUMNS if c in feat_df.columns]
        valid = feat_df[available].notna().all(axis=1)
        if not feat_df[valid].empty:
            feat_row = feat_df[valid].iloc[-1]
            # Merge battery features into feat_row for battery regime detection
            if not batt_df.empty:
                batt_row = batt_df.iloc[-1]
                for col in ["battery_saturation_proxy", "storage_charge_pressure",
                            "storage_discharge_pressure", "expected_battery_absorption",
                            "expected_battery_release"]:
                    if col in batt_row.index:
                        feat_row[col] = batt_row[col]
            clf    = RegimeClassifier()
            regime = clf.classify(feat_row)
            regime_info = {
                "regime":            regime.regime.value,
                "confidence":        regime.confidence,
                "signal_thresholds": regime.signal_thresholds,
                "description":       regime.description,
            }
        else:
            regime_info = {"regime": "UNKNOWN", "confidence": 0.0, "signal_thresholds": {}, "description": ""}

        batt_state = {}
        if not batt_df.empty:
            row = batt_df.iloc[-1]
            for col in ["battery_saturation_proxy", "storage_charge_pressure",
                        "storage_discharge_pressure", "net_battery_flow_mw",
                        "expected_battery_absorption", "expected_battery_release"]:
                val = row.get(col)
                batt_state[col] = round(float(val), 4) if val is not None and str(val) != "nan" else None

        return {
            "regime":             regime_info,
            "battery_state":      batt_state,
            "hc_signal_blocked":  (batt_state.get("battery_saturation_proxy", 0) or 0) >= 0.85
                                  or (batt_state.get("expected_battery_absorption", 0) or 0) >= 8000,
            "generated_at":       datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("GET /battery/regime-impact failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/data-quality", summary="Battery data source quality report")
async def get_battery_data_quality(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Report on battery data availability and quality scores."""
    try:
        df = await _fetch_price_df(db, hours=24)
        if not df.empty:
            batt_df = await _svc.get_battery_features(df)
        else:
            batt_df = pd.DataFrame()
        return await _svc.get_data_quality_report(batt_df)
    except Exception as exc:
        logger.exception("GET /battery/data-quality failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
