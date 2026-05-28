"""
Data ingestion and retrieval routes.

POST /data/ingest  – trigger DataIngestionService.ingest_recent()
GET  /data/latest  – last 48 h of HourlyPrice records
GET  /data/quality – DataQualityResult for the primary data source
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.db.models import HourlyPrice, DataQualityLog
from app.api.schemas import (
    DataPoint,
    DataQualityResponse,
    IngestRequest,
    IngestResponse,
)

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model_to_datapoint(row: HourlyPrice) -> DataPoint:
    return DataPoint(
        timestamp=row.timestamp,
        source=row.source,
        price_eur_mwh=row.price_eur_mwh,
        intraday_price_eur_mwh=row.intraday_price_eur_mwh,
        load_mw=row.load_mw,
        wind_onshore_mw=row.wind_onshore_mw,
        wind_offshore_mw=row.wind_offshore_mw,
        solar_mw=row.solar_mw,
        residual_load_mw=row.residual_load_mw,
        net_export_mw=row.net_export_mw,
        temperature_c=row.temperature_c,
        wind_speed_ms=row.wind_speed_ms,
        solar_radiation_wm2=row.solar_radiation_wm2,
        cloud_cover_pct=row.cloud_cover_pct,
        is_holiday=bool(row.is_holiday),
        is_weekend=bool(row.is_weekend),
        hour=row.hour,
        month=row.month,
    )


async def _run_quality_check(db: AsyncSession, source: str = "smard") -> DataQualityResponse:
    """Inspect the DB for data freshness and completeness."""
    now = datetime.now(timezone.utc)

    stmt = (
        select(HourlyPrice)
        .where(HourlyPrice.source == source)
        .order_by(HourlyPrice.timestamp.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    latest: Optional[HourlyPrice] = result.scalar_one_or_none()

    issues: List[str] = []
    missing_fields: List[str] = []

    if latest is None:
        return DataQualityResponse(
            checked_at=now,
            source=source,
            latest_timestamp=None,
            age_minutes=None,
            is_fresh=False,
            missing_fields=[],
            issues=["No data found in database for source: " + source],
            row_count_last_24h=0,
        )

    latest_ts = latest.timestamp
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.replace(tzinfo=timezone.utc)
    age_minutes = (now - latest_ts).total_seconds() / 60.0

    # Check fields for completeness on latest row
    optional_fields = [
        "price_eur_mwh",
        "load_mw",
        "wind_onshore_mw",
        "wind_offshore_mw",
        "solar_mw",
        "residual_load_mw",
        "temperature_c",
        "wind_speed_ms",
    ]
    for field in optional_fields:
        if getattr(latest, field, None) is None:
            missing_fields.append(field)

    max_age_minutes = 90
    is_fresh = age_minutes <= max_age_minutes

    if not is_fresh:
        issues.append(
            f"Data is stale: latest timestamp is {age_minutes:.0f} minutes old "
            f"(threshold: {max_age_minutes} min)"
        )
    if missing_fields:
        issues.append(f"Latest row is missing fields: {', '.join(missing_fields)}")

    # Row count last 24h
    cutoff_24h = now - timedelta(hours=24)
    count_stmt = select(func.count()).select_from(HourlyPrice).where(
        HourlyPrice.source == source,
        HourlyPrice.timestamp >= cutoff_24h,
    )
    count_result = await db.execute(count_stmt)
    row_count = count_result.scalar_one()

    if row_count < 20:
        issues.append(f"Only {row_count} rows in the last 24 hours (expected ~24)")

    return DataQualityResponse(
        checked_at=now,
        source=source,
        latest_timestamp=latest_ts,
        age_minutes=round(age_minutes, 1),
        is_fresh=is_fresh,
        missing_fields=missing_fields,
        issues=issues,
        row_count_last_24h=row_count,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse, summary="Trigger data ingestion")
async def ingest_data(
    request: IngestRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Trigger a full data ingestion run: prices (aWATTar) + weather (Open-Meteo).
    Upserts all rows including weather columns.
    """
    t0 = time.monotonic()
    errors: List[str] = []

    from app.data.smard import fetch_recent
    from app.data import openmeteo
    from app.data.ingestion import _merge_sources, _df_to_rows, HOURLY_WEATHER_COLUMNS
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import pandas as pd

    hours_back = 72
    if request.start_date and request.end_date:
        delta = request.end_date - request.start_date
        hours_back = max(int(delta.total_seconds() / 3600), 1)
    elif hasattr(request, "hours_back") and request.hours_back:
        hours_back = request.hours_back

    try:
        smard_df, weather_df = await asyncio.gather(
            fetch_recent(hours_back=hours_back),
            openmeteo.fetch_historical(hours_back=hours_back),
            return_exceptions=True,
        )
        if isinstance(smard_df, Exception):
            errors.append(f"Price fetch: {smard_df}")
            smard_df = pd.DataFrame()
        if isinstance(weather_df, Exception):
            errors.append(f"Weather fetch: {weather_df}")
            weather_df = pd.DataFrame()

        merged = _merge_sources(smard_df, pd.DataFrame(), weather_df)

        rows_inserted = 0
        rows_updated = 0
        if not merged.empty:
            from datetime import timezone as _tz
            from app.data.holidays import is_german_holiday, is_weekend as _is_weekend

            rows_to_upsert = []
            for ts, row in merged.iterrows():
                ts_naive = pd.Timestamp(ts).to_pydatetime().replace(tzinfo=None)
                ts_aware = ts_naive.replace(tzinfo=_tz.utc)
                wk = ts_naive.weekday()

                def sf(v):
                    try:
                        return float(v) if v is not None and not pd.isna(v) else None
                    except Exception:
                        return None

                wind_on = sf(row.get("wind_onshore_mw"))
                wind_off = sf(row.get("wind_offshore_mw"))
                solar = sf(row.get("solar_mw"))
                load = sf(row.get("load_mw"))
                residual = None
                if all(v is not None for v in [load, wind_on, solar]):
                    residual = load - (wind_on or 0) - (wind_off or 0) - solar

                record = {
                    "timestamp": ts_aware,
                    "source": "smard",
                    "price_eur_mwh": sf(row.get("price_eur_mwh")),
                    "load_mw": load,
                    "wind_onshore_mw": wind_on,
                    "wind_offshore_mw": wind_off,
                    "solar_mw": solar,
                    "residual_load_mw": residual,
                    "temperature_c": sf(row.get("temperature_c")),
                    "wind_speed_ms": sf(row.get("wind_speed_ms")),
                    "solar_radiation_wm2": sf(row.get("solar_radiation_wm2")),
                    "cloud_cover_pct": sf(row.get("cloud_cover_pct")),
                    "is_weekend": wk >= 5,
                    "is_holiday": is_german_holiday(ts_naive),
                    "hour": ts_naive.hour,
                    "month": ts_naive.month,
                }
                rows_to_upsert.append(record)

            if rows_to_upsert:
                stmt = (
                    pg_insert(HourlyPrice)
                    .values(rows_to_upsert)
                    .on_conflict_do_update(
                        index_elements=["timestamp"],
                        set_={k: pg_insert(HourlyPrice).excluded[k]
                              for k in rows_to_upsert[0] if k != "timestamp"},
                    )
                )
                await db.execute(stmt)
                await db.commit()
                rows_inserted = len(rows_to_upsert)

    except Exception as exc:
        logger.exception("Ingestion error: %s", exc)
        errors.append(str(exc))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")

    duration = time.monotonic() - t0
    logger.info("Ingest: %d rows upserted in %.2fs", rows_inserted, duration)
    return IngestResponse(
        source=request.source,
        rows_inserted=rows_inserted,
        rows_updated=rows_updated,
        start_date=request.start_date,
        end_date=request.end_date,
        duration_seconds=round(duration, 3),
        errors=errors,
    )



@router.get("/latest", response_model=List[DataPoint], summary="Latest 48h of market data")
async def get_latest_data(
    hours: int = Query(default=48, ge=1, le=720, description="Hours of history to return"),
    source: str = Query(default="smard", description="Data source filter"),
    db: AsyncSession = Depends(get_db),
) -> List[DataPoint]:
    """
    Return hourly market data records from the last N hours.

    Defaults to 48 hours from the primary SMARD source.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    stmt = (
        select(HourlyPrice)
        .where(
            HourlyPrice.timestamp >= cutoff,
            HourlyPrice.source == source,
        )
        .order_by(HourlyPrice.timestamp.asc())
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    logger.info("GET /data/latest: returning %d rows for last %dh", len(rows), hours)
    return [_model_to_datapoint(r) for r in rows]


@router.get("/quality", response_model=DataQualityResponse, summary="Data quality check")
async def get_data_quality(
    source: str = Query(default="smard", description="Data source to check"),
    db: AsyncSession = Depends(get_db),
) -> DataQualityResponse:
    """
    Run a data freshness and completeness check against the database.

    Returns staleness metrics, missing field counts, and an overall freshness flag.
    """
    return await _run_quality_check(db, source=source)
