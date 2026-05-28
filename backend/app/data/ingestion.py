"""
Data ingestion orchestrator.

Coordinates fetching from SMARD, ENTSO-E, Open-Meteo, and the German holiday
calendar, merges results on UTC timestamp, validates data quality, and persists
the merged records to PostgreSQL via SQLAlchemy async sessions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.data import smard, entsoe, openmeteo
from app.data.holidays import get_calendar_features
from app.db.models import HourlyPrice, DataQualityLog

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data quality result type
# ---------------------------------------------------------------------------

@dataclass
class SourceStatus:
    """Per-source health information."""
    name: str
    ok: bool
    rows_fetched: int = 0
    error: Optional[str] = None


@dataclass
class DataQualityResult:
    """Aggregated data quality assessment."""
    is_fresh: bool
    age_minutes: Optional[float]    # Minutes since the most recent row in DB
    missing_fields: list[str]       # Columns with > threshold % missing values
    issues: list[str]               # Human-readable issue descriptions
    source_status: list[SourceStatus]
    checked_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum acceptable age of the most recent DB row (in minutes)
_MAX_FRESHNESS_MINUTES = 90

# Percentage of NaN values above which a column is flagged as "missing"
_MISSING_THRESHOLD_PCT = 20.0

# Columns that must be present in the merged DataFrame
_REQUIRED_COLUMNS = [
    "price_eur_mwh",
    "load_mw",
    "wind_onshore_mw",
    "wind_offshore_mw",
    "solar_mw",
    "temperature_c",
    "wind_speed_ms",
    "solar_radiation_wm2",
    "cloud_cover_pct",
]

# ---------------------------------------------------------------------------
# Merge & feature engineering helpers
# ---------------------------------------------------------------------------

def _add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach calendar feature columns derived from the timestamp index."""
    features_list = [get_calendar_features(ts) for ts in df.index]
    features_df = pd.DataFrame(features_list, index=df.index)
    return df.join(features_df, how="left")


def _merge_sources(
    smard_df: pd.DataFrame,
    entsoe_prices_df: pd.DataFrame,
    weather_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge SMARD, ENTSO-E, and weather DataFrames on UTC timestamp index.

    Strategy:
    - SMARD prices are the primary price source.
    - ENTSO-E prices fill in gaps where SMARD price is NaN.
    - Weather data is joined on timestamp; unmatched hours remain NaN.
    """
    def _to_indexed(df: pd.DataFrame) -> pd.DataFrame:
        """Set timestamp as UTC-naive DatetimeIndex, dropping the column."""
        if df is None or (hasattr(df, "empty") and df.empty):
            return pd.DataFrame()
        d = df.copy()
        if "timestamp" in d.columns:
            d["timestamp"] = pd.to_datetime(d["timestamp"]).dt.tz_localize(None).dt.floor("h")
            d = d.set_index("timestamp")
        elif d.index.name == "timestamp" or isinstance(d.index, pd.DatetimeIndex):
            idx = pd.to_datetime(d.index)
            if idx.tz is not None:
                idx = idx.tz_convert("UTC").tz_localize(None)
            d.index = idx.floor("h")
            d.index.name = "timestamp"
        return d

    # Normalise all inputs to UTC-naive timestamp index
    smard_df = _to_indexed(smard_df)
    entsoe_prices_df = _to_indexed(entsoe_prices_df)
    weather_df = _to_indexed(weather_df)

    # Start with SMARD as the base
    if smard_df.empty:
        merged = pd.DataFrame()
    else:
        merged = smard_df.copy()

    # Backfill price gaps from ENTSO-E if available
    if not entsoe_prices_df.empty and not merged.empty:
        if "price_eur_mwh" in entsoe_prices_df.columns:
            entsoe_aligned = entsoe_prices_df[["price_eur_mwh"]].rename(
                columns={"price_eur_mwh": "_entsoe_price"}
            )
            merged = merged.join(entsoe_aligned, how="left")
            mask = merged["price_eur_mwh"].isna() & merged["_entsoe_price"].notna()
            merged.loc[mask, "price_eur_mwh"] = merged.loc[mask, "_entsoe_price"]
            merged.drop(columns=["_entsoe_price"], inplace=True)
    elif not entsoe_prices_df.empty and merged.empty:
        merged = entsoe_prices_df.copy()

    # Join weather data on the shared UTC-naive hourly index
    if not weather_df.empty and not merged.empty:
        weather_cols = [c for c in HOURLY_WEATHER_COLUMNS if c in weather_df.columns]
        merged = merged.join(weather_df[weather_cols], how="left")
    elif not weather_df.empty and merged.empty:
        merged = weather_df.copy()

    return merged.sort_index()


HOURLY_WEATHER_COLUMNS = [
    "temperature_c",
    "wind_speed_ms",
    "solar_radiation_wm2",
    "cloud_cover_pct",
]

# ---------------------------------------------------------------------------
# Data quality validation
# ---------------------------------------------------------------------------

def _validate_dataframe(df: pd.DataFrame) -> list[str]:
    """
    Inspect *df* for quality issues.

    Returns a list of human-readable issue descriptions.
    """
    issues: list[str] = []

    if df.empty:
        issues.append("Merged DataFrame is empty — no data to persist")
        return issues

    # Check for expected columns
    for col in _REQUIRED_COLUMNS:
        if col not in df.columns:
            issues.append(f"Column '{col}' is missing from merged data")

    # Check for high NaN rates
    for col in _REQUIRED_COLUMNS:
        if col not in df.columns:
            continue
        nan_pct = 100.0 * df[col].isna().mean()
        if nan_pct > _MISSING_THRESHOLD_PCT:
            issues.append(
                f"Column '{col}' has {nan_pct:.1f}% NaN values "
                f"(threshold {_MISSING_THRESHOLD_PCT:.0f}%)"
            )

    # Check for timestamp gaps
    if len(df) > 1:
        diffs = pd.Series(df.index).diff().dropna()
        expected_delta = pd.Timedelta(hours=1)
        gaps = diffs[diffs > expected_delta * 1.5]
        if not gaps.empty:
            issues.append(
                f"{len(gaps)} timestamp gap(s) larger than 1.5 hours detected"
            )

    # Check for suspicious price values
    if "price_eur_mwh" in df.columns:
        valid_prices = df["price_eur_mwh"].dropna()
        if len(valid_prices) > 0:
            if (valid_prices > 3000).any():
                issues.append(
                    "Extreme price spike detected: max "
                    f"{valid_prices.max():.1f} €/MWh (> 3000 €/MWh)"
                )
            if (valid_prices < -500).any():
                issues.append(
                    "Deeply negative price detected: min "
                    f"{valid_prices.min():.1f} €/MWh (< -500 €/MWh)"
                )

    return issues


def _missing_fields(df: pd.DataFrame) -> list[str]:
    """Return list of columns with > threshold NaN percentage."""
    missing: list[str] = []
    for col in _REQUIRED_COLUMNS:
        if col not in df.columns:
            missing.append(col)
            continue
        nan_pct = 100.0 * df[col].isna().mean()
        if nan_pct > _MISSING_THRESHOLD_PCT:
            missing.append(col)
    return missing


# ---------------------------------------------------------------------------
# Database persistence helpers
# ---------------------------------------------------------------------------

async def _upsert_rows(db: AsyncSession, rows: list[dict]) -> int:
    """
    Upsert *rows* into the ``hourly_prices`` table.

    Uses PostgreSQL ``INSERT … ON CONFLICT (timestamp) DO UPDATE`` semantics
    so duplicate timestamps are updated rather than raising an error.

    Returns the number of rows upserted.
    """
    if not rows:
        return 0

    stmt = (
        pg_insert(HourlyPrice)
        .values(rows)
        .on_conflict_do_update(
            index_elements=["timestamp"],
            set_={
                col: pg_insert(HourlyPrice).excluded.__getattr__(col)
                for col in rows[0].keys()
                if col != "timestamp"
            },
        )
    )
    await db.execute(stmt)
    return len(rows)


def _df_to_rows(df: pd.DataFrame) -> list[dict]:
    """Convert the merged DataFrame (timestamp-indexed) to a list of dicts for DB insertion."""
    rows: list[dict] = []
    for ts, row in df.iterrows():
        ts_obj = pd.Timestamp(ts).to_pydatetime()
        # Keep UTC timezone so PostgreSQL stores at correct UTC offset
        ts_clean = ts_obj if ts_obj.tzinfo is not None else ts_obj.replace(tzinfo=timezone.utc)
        record: dict[str, Any] = {"timestamp": ts_clean}
        for col in _REQUIRED_COLUMNS:
            val = row.get(col)
            # Store pandas NA/NaN as Python None
            record[col] = None if pd.isna(val) else float(val)

        # Calendar features (store day_type string and boolean flags)
        for bool_col in ["is_holiday", "is_weekend", "is_bridge_day", "is_non_working"]:
            val = row.get(bool_col)
            record[bool_col] = None if pd.isna(val) else bool(val)

        for int_col in ["day_of_week", "hour_of_day", "month"]:
            val = row.get(int_col)
            record[int_col] = None if pd.isna(val) else int(val)

        record["day_type"] = row.get("day_type")
        record["holiday_name"] = row.get("holiday_name")

        rows.append(record)
    return rows


async def _log_quality(
    db: AsyncSession,
    result: DataQualityResult,
    rows_upserted: int,
) -> None:
    """Write a DataQualityLog entry after an ingestion run."""
    try:
        log_entry = DataQualityLog(
            checked_at=result.checked_at,
            is_fresh=result.is_fresh,
            age_minutes=result.age_minutes,
            missing_fields=result.missing_fields,
            issues=result.issues,
            rows_upserted=rows_upserted,
        )
        db.add(log_entry)
    except Exception as exc:  # noqa: BLE001
        # Do not let logging failure abort the ingestion
        logger.warning("Failed to write DataQualityLog entry: %s", exc)


# ---------------------------------------------------------------------------
# Public service class
# ---------------------------------------------------------------------------

class DataIngestionService:
    """
    Orchestrates data fetching, merging, validation, and persistence.

    Usage
    -----
    .. code-block:: python

        service = DataIngestionService()

        async with AsyncSession(engine) as db:
            stats = await service.ingest_recent(hours_back=48, db=db)
            quality = await service.check_data_quality(db=db)
    """

    # ------------------------------------------------------------------
    # ingest_recent
    # ------------------------------------------------------------------

    async def ingest_recent(
        self,
        hours_back: int = 48,
        db: AsyncSession = None,
    ) -> dict[str, Any]:
        """
        Fetch, merge, validate, and persist recent electricity market data.

        Parameters
        ----------
        hours_back:
            Number of past hours to fetch from each upstream source.
        db:
            SQLAlchemy async session.  Must be provided.

        Returns
        -------
        dict
            Ingestion statistics:
            - ``rows_fetched`` : int — total rows in merged DataFrame
            - ``rows_upserted`` : int — rows written/updated in DB
            - ``smard_rows`` : int
            - ``entsoe_rows`` : int
            - ``weather_rows`` : int
            - ``issues`` : list[str] — data quality issues found
            - ``duration_seconds`` : float
        """
        if db is None:
            raise ValueError("A SQLAlchemy AsyncSession must be provided via 'db='")

        import time as _time
        t0 = _time.monotonic()

        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(hours=hours_back)

        logger.info(
            "DataIngestionService.ingest_recent: fetching %d hours back from %s UTC",
            hours_back,
            start.strftime("%Y-%m-%d %H:%M"),
        )

        source_status: list[SourceStatus] = []

        # ---- Fetch SMARD ------------------------------------------------
        smard_df = pd.DataFrame()
        try:
            smard_df = await smard.fetch_recent(hours_back=hours_back)
            source_status.append(
                SourceStatus(name="smard", ok=True, rows_fetched=len(smard_df))
            )
            logger.info("SMARD: %d rows fetched", len(smard_df))
        except Exception as exc:  # noqa: BLE001
            logger.error("SMARD fetch error: %s", exc)
            source_status.append(
                SourceStatus(name="smard", ok=False, error=str(exc))
            )

        # ---- Fetch ENTSO-E prices ----------------------------------------
        entsoe_prices_df = pd.DataFrame()
        try:
            entsoe_prices_df = await entsoe.fetch_day_ahead_prices(
                start=start, end=now
            )
            source_status.append(
                SourceStatus(
                    name="entsoe_prices", ok=True, rows_fetched=len(entsoe_prices_df)
                )
            )
            logger.info("ENTSO-E prices: %d rows fetched", len(entsoe_prices_df))
        except Exception as exc:  # noqa: BLE001
            logger.error("ENTSO-E price fetch error: %s", exc)
            source_status.append(
                SourceStatus(name="entsoe_prices", ok=False, error=str(exc))
            )

        # ---- Fetch Open-Meteo weather ------------------------------------
        weather_df = pd.DataFrame()
        try:
            weather_df = await openmeteo.fetch_historical(hours_back=hours_back)
            source_status.append(
                SourceStatus(
                    name="openmeteo", ok=True, rows_fetched=len(weather_df)
                )
            )
            logger.info("Open-Meteo: %d rows fetched", len(weather_df))
        except Exception as exc:  # noqa: BLE001
            logger.error("Open-Meteo fetch error: %s", exc)
            source_status.append(
                SourceStatus(name="openmeteo", ok=False, error=str(exc))
            )

        # ---- Merge -------------------------------------------------------
        merged = _merge_sources(smard_df, entsoe_prices_df, weather_df)

        if not merged.empty:
            merged = _add_calendar_features(merged)

        # ---- Validate ----------------------------------------------------
        issues = _validate_dataframe(merged)
        if issues:
            for issue in issues:
                logger.warning("Data quality issue: %s", issue)

        # ---- Persist to DB -----------------------------------------------
        rows_upserted = 0
        if not merged.empty:
            rows = _df_to_rows(merged)
            try:
                rows_upserted = await _upsert_rows(db, rows)
                await db.commit()
                logger.info(
                    "Upserted %d rows into hourly_prices", rows_upserted
                )
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                logger.error("DB upsert failed: %s", exc)
                issues.append(f"DB upsert failed: {exc}")

        # ---- Write quality log -------------------------------------------
        quality_result = DataQualityResult(
            is_fresh=not merged.empty,
            age_minutes=None,
            missing_fields=_missing_fields(merged) if not merged.empty else list(_REQUIRED_COLUMNS),
            issues=issues,
            source_status=source_status,
        )
        await _log_quality(db, quality_result, rows_upserted)
        try:
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to commit quality log: %s", exc)

        duration = _time.monotonic() - t0

        stats: dict[str, Any] = {
            "rows_fetched": len(merged),
            "rows_upserted": rows_upserted,
            "smard_rows": len(smard_df),
            "entsoe_rows": len(entsoe_prices_df),
            "weather_rows": len(weather_df),
            "issues": issues,
            "duration_seconds": round(duration, 2),
        }

        logger.info(
            "Ingestion complete in %.2fs: %d rows merged, %d upserted, %d issues",
            duration,
            len(merged),
            rows_upserted,
            len(issues),
        )
        return stats

    # ------------------------------------------------------------------
    # check_data_quality
    # ------------------------------------------------------------------

    async def check_data_quality(
        self,
        db: AsyncSession = None,
    ) -> DataQualityResult:
        """
        Inspect the current state of the ``hourly_prices`` table and return
        a :class:`DataQualityResult` describing freshness and completeness.

        Parameters
        ----------
        db:
            SQLAlchemy async session.

        Returns
        -------
        DataQualityResult
        """
        if db is None:
            raise ValueError("A SQLAlchemy AsyncSession must be provided via 'db='")

        now = datetime.now(tz=timezone.utc)
        issues: list[str] = []
        age_minutes: Optional[float] = None
        is_fresh = False

        # ---- Check most recent row ----------------------------------------
        try:
            result = await db.execute(
                select(HourlyPrice.timestamp)
                .order_by(HourlyPrice.timestamp.desc())
                .limit(1)
            )
            latest_ts = result.scalar_one_or_none()

            if latest_ts is None:
                issues.append("No rows found in hourly_prices — table is empty")
            else:
                if latest_ts.tzinfo is None:
                    latest_ts = latest_ts.replace(tzinfo=timezone.utc)
                age_minutes = (now - latest_ts).total_seconds() / 60.0
                is_fresh = age_minutes <= _MAX_FRESHNESS_MINUTES

                if not is_fresh:
                    issues.append(
                        f"Data is stale: most recent row is {age_minutes:.1f} minutes old "
                        f"(threshold: {_MAX_FRESHNESS_MINUTES} min)"
                    )
                else:
                    logger.debug(
                        "Data freshness OK: latest row %.1f minutes old", age_minutes
                    )

        except Exception as exc:  # noqa: BLE001
            logger.error("DB freshness check failed: %s", exc)
            issues.append(f"DB freshness check failed: {exc}")

        # ---- Column-level NaN check on recent rows ----------------------
        missing: list[str] = []
        try:
            window_start = now - timedelta(hours=48)
            result = await db.execute(
                select(HourlyPrice)
                .where(HourlyPrice.timestamp >= window_start)
                .order_by(HourlyPrice.timestamp.asc())
            )
            recent_rows = result.scalars().all()

            if recent_rows:
                # Build a quick DataFrame from ORM objects for vectorised checks
                row_dicts = [
                    {col: getattr(r, col, None) for col in _REQUIRED_COLUMNS}
                    for r in recent_rows
                ]
                df_check = pd.DataFrame(row_dicts)

                for col in _REQUIRED_COLUMNS:
                    if col not in df_check.columns:
                        missing.append(col)
                        issues.append(f"Column '{col}' not present in DB model")
                        continue
                    nan_pct = 100.0 * df_check[col].isna().mean()
                    if nan_pct > _MISSING_THRESHOLD_PCT:
                        missing.append(col)
                        issues.append(
                            f"'{col}': {nan_pct:.1f}% NaN in the last 48 h "
                            f"(threshold {_MISSING_THRESHOLD_PCT:.0f}%)"
                        )
            else:
                issues.append("No rows in the last 48 hours — recent data unavailable")
                missing = list(_REQUIRED_COLUMNS)

        except Exception as exc:  # noqa: BLE001
            logger.error("DB column quality check failed: %s", exc)
            issues.append(f"DB column quality check failed: {exc}")

        source_status: list[SourceStatus] = []
        # We don't re-fetch live sources here — report unknown status
        for src in ["smard", "entsoe_prices", "openmeteo"]:
            source_status.append(SourceStatus(name=src, ok=True, rows_fetched=-1))

        result_obj = DataQualityResult(
            is_fresh=is_fresh,
            age_minutes=age_minutes,
            missing_fields=missing,
            issues=issues,
            source_status=source_status,
        )

        log_level = logger.info if is_fresh and not issues else logger.warning
        log_level(
            "Data quality check: fresh=%s, age=%.1f min, %d issue(s)",
            is_fresh,
            age_minutes if age_minutes is not None else -1.0,
            len(issues),
        )
        return result_obj
