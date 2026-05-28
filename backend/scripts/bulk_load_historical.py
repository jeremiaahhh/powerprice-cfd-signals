#!/usr/bin/env python3
"""
Bulk historical data loader.

Fetches month-by-month from Jan 2024 → today using:
  - aWATTar DE API  (EPEX SPOT Day-Ahead prices, free)
  - Open-Meteo archive API  (ERA5 reanalysis weather, free)

Upserts all rows into hourly_prices via ON CONFLICT (timestamp) DO UPDATE.

Run from backend/ directory:
    python scripts/bulk_load_historical.py
"""
from __future__ import annotations

import sys
import time
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd
import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_DSN = "postgresql://ppuser:pppass@localhost:5432/powerprice"

AWATTAR_URL = "https://api.awattar.de/v1/marketdata"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Germany centre-of-mass coordinates
LAT, LON = 51.5, 10.0

# Start month (inclusive)
LOAD_FROM = datetime(2024, 1, 1, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# aWATTar price fetch
# ---------------------------------------------------------------------------

def fetch_awattar_month(start: datetime, end: datetime) -> pd.DataFrame:
    """Return DataFrame(timestamp_utc_naive, price_eur_mwh) for [start, end)."""
    params = {
        "start": int(start.timestamp() * 1000),
        "end":   int(end.timestamp() * 1000),
    }
    for attempt in range(3):
        try:
            r = httpx.get(AWATTAR_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json().get("data", [])
            break
        except Exception as exc:
            if attempt == 2:
                print(f"    aWATTar error: {exc}")
                return pd.DataFrame(columns=["timestamp", "price_eur_mwh"])
            time.sleep(2 ** attempt)

    rows = []
    for entry in data:
        ts = datetime.fromtimestamp(entry["start_timestamp"] / 1000, tz=timezone.utc)
        ts_naive = ts.replace(tzinfo=None)
        price = entry.get("marketprice")
        if price is not None:
            rows.append({"timestamp": ts_naive, "price_eur_mwh": float(price)})

    if not rows:
        return pd.DataFrame(columns=["timestamp", "price_eur_mwh"])

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.floor("h")
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Open-Meteo archive weather fetch
# ---------------------------------------------------------------------------

def fetch_openmeteo_month(start: datetime, end: datetime) -> pd.DataFrame:
    """Return weather DataFrame indexed by UTC-naive hourly timestamp."""
    # end_date is inclusive in archive API — use last day of the month
    end_date = (end - timedelta(days=1)).strftime("%Y-%m-%d")
    params = {
        "latitude":  LAT,
        "longitude": LON,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date":   end_date,
        "hourly": "temperature_2m,wind_speed_10m,shortwave_radiation,cloud_cover",
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    for attempt in range(3):
        try:
            r = httpx.get(ARCHIVE_URL, params=params, timeout=60)
            r.raise_for_status()
            payload = r.json()
            if payload.get("error"):
                raise ValueError(payload.get("reason", "Open-Meteo error"))
            break
        except Exception as exc:
            if attempt == 2:
                print(f"    Open-Meteo error: {exc}")
                return pd.DataFrame()
            time.sleep(2 ** attempt)

    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return pd.DataFrame()

    df = pd.DataFrame({
        "timestamp":          pd.to_datetime(times).floor("h").tz_localize(None),
        "temperature_c":      pd.to_numeric(hourly.get("temperature_2m",     [None]*len(times)), errors="coerce"),
        "wind_speed_ms":      pd.to_numeric(hourly.get("wind_speed_10m",     [None]*len(times)), errors="coerce"),
        "solar_radiation_wm2":pd.to_numeric(hourly.get("shortwave_radiation",[None]*len(times)), errors="coerce"),
        "cloud_cover_pct":    pd.to_numeric(hourly.get("cloud_cover",        [None]*len(times)), errors="coerce"),
    })
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df


# ---------------------------------------------------------------------------
# Proxy generation from weather
# ---------------------------------------------------------------------------

def add_generation_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """Derive load/wind/solar proxy columns from weather if not present."""
    if "wind_speed_ms" in df.columns:
        ws = df["wind_speed_ms"].fillna(0)
        df["wind_onshore_mw"]  = (ws ** 2.5 * 400).clip(0, 65000)
        df["wind_offshore_mw"] = (ws ** 2.5 * 90).clip(0, 9000)
    else:
        df["wind_onshore_mw"]  = None
        df["wind_offshore_mw"] = None

    if "solar_radiation_wm2" in df.columns:
        df["solar_mw"] = (df["solar_radiation_wm2"].fillna(0) * 60.0).clip(0, 70000)
    else:
        df["solar_mw"] = None

    if "temperature_c" in df.columns:
        df["load_mw"] = (55000 + (15 - df["temperature_c"].fillna(15)) * 800).clip(35000, 90000)
    else:
        df["load_mw"] = None

    return df


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO hourly_prices (
    timestamp, source, price_eur_mwh,
    load_mw, wind_onshore_mw, wind_offshore_mw, solar_mw, residual_load_mw,
    temperature_c, wind_speed_ms, solar_radiation_wm2, cloud_cover_pct,
    is_holiday, is_weekend, hour, month
) VALUES %s
ON CONFLICT (timestamp) DO UPDATE SET
    price_eur_mwh        = EXCLUDED.price_eur_mwh,
    load_mw              = EXCLUDED.load_mw,
    wind_onshore_mw      = EXCLUDED.wind_onshore_mw,
    wind_offshore_mw     = EXCLUDED.wind_offshore_mw,
    solar_mw             = EXCLUDED.solar_mw,
    residual_load_mw     = EXCLUDED.residual_load_mw,
    temperature_c        = EXCLUDED.temperature_c,
    wind_speed_ms        = EXCLUDED.wind_speed_ms,
    solar_radiation_wm2  = EXCLUDED.solar_radiation_wm2,
    cloud_cover_pct      = EXCLUDED.cloud_cover_pct,
    is_holiday           = EXCLUDED.is_holiday,
    is_weekend           = EXCLUDED.is_weekend,
    hour                 = EXCLUDED.hour,
    month                = EXCLUDED.month
"""


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except Exception:
        return None


def is_german_holiday(dt: datetime) -> bool:
    """Simplified German federal public holidays (nationwide only)."""
    m, d = dt.month, dt.day
    fixed = {(1,1),(5,1),(10,3),(12,25),(12,26)}
    if (m, d) in fixed:
        return True
    # Easter-based: Good Friday, Easter Monday, Ascension, Whit Monday
    from datetime import date
    y = dt.year
    # Anonymous Gregorian algorithm
    a = y % 19; b = y // 100; c = y % 100
    d_ = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19*a + b - d_ - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2*e + 2*i - h - k) % 7
    m_ = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m_ + 114) // 31
    day = ((h + l - 7*m_ + 114) % 31) + 1
    easter = date(y, month, day)
    specials = {
        easter - timedelta(days=2),   # Good Friday
        easter + timedelta(days=1),   # Easter Monday
        easter + timedelta(days=39),  # Ascension
        easter + timedelta(days=50),  # Whit Monday
    }
    return date(y, dt.month, dt.day) in specials


_ROW_UPSERT_SQL = """
INSERT INTO hourly_prices (
    timestamp, source, price_eur_mwh,
    load_mw, wind_onshore_mw, wind_offshore_mw, solar_mw, residual_load_mw,
    temperature_c, wind_speed_ms, solar_radiation_wm2, cloud_cover_pct,
    is_holiday, is_weekend, hour, month
) VALUES (
    %(timestamp)s, %(source)s, %(price_eur_mwh)s,
    %(load_mw)s, %(wind_onshore_mw)s, %(wind_offshore_mw)s, %(solar_mw)s, %(residual_load_mw)s,
    %(temperature_c)s, %(wind_speed_ms)s, %(solar_radiation_wm2)s, %(cloud_cover_pct)s,
    %(is_holiday)s, %(is_weekend)s, %(hour)s, %(month)s
)
ON CONFLICT (timestamp) DO UPDATE SET
    price_eur_mwh        = EXCLUDED.price_eur_mwh,
    load_mw              = EXCLUDED.load_mw,
    wind_onshore_mw      = EXCLUDED.wind_onshore_mw,
    wind_offshore_mw     = EXCLUDED.wind_offshore_mw,
    solar_mw             = EXCLUDED.solar_mw,
    residual_load_mw     = EXCLUDED.residual_load_mw,
    temperature_c        = EXCLUDED.temperature_c,
    wind_speed_ms        = EXCLUDED.wind_speed_ms,
    solar_radiation_wm2  = EXCLUDED.solar_radiation_wm2,
    cloud_cover_pct      = EXCLUDED.cloud_cover_pct,
    is_holiday           = EXCLUDED.is_holiday,
    is_weekend           = EXCLUDED.is_weekend,
    hour                 = EXCLUDED.hour,
    month                = EXCLUDED.month
"""


def upsert_month(conn, merged: pd.DataFrame) -> int:
    if merged.empty:
        return 0

    # Deduplicate on timestamp index (keep last, which has most data)
    merged = merged[~merged.index.duplicated(keep="last")]

    seen: dict = {}
    for ts, row in merged.iterrows():
        dt = pd.Timestamp(ts).to_pydatetime().replace(tzinfo=None)
        key = dt.replace(second=0, microsecond=0)

        load      = _safe_float(row.get("load_mw"))
        wind_on   = _safe_float(row.get("wind_onshore_mw"))
        wind_off  = _safe_float(row.get("wind_offshore_mw"))
        solar     = _safe_float(row.get("solar_mw"))
        residual  = None
        if all(v is not None for v in [load, wind_on, solar]):
            residual = load - (wind_on or 0) - (wind_off or 0) - solar

        seen[key] = {
            "timestamp":           dt,
            "source":              "smard",
            "price_eur_mwh":       _safe_float(row.get("price_eur_mwh")),
            "load_mw":             load,
            "wind_onshore_mw":     wind_on,
            "wind_offshore_mw":    wind_off,
            "solar_mw":            solar,
            "residual_load_mw":    residual,
            "temperature_c":       _safe_float(row.get("temperature_c")),
            "wind_speed_ms":       _safe_float(row.get("wind_speed_ms")),
            "solar_radiation_wm2": _safe_float(row.get("solar_radiation_wm2")),
            "cloud_cover_pct":     _safe_float(row.get("cloud_cover_pct")),
            "is_holiday":          is_german_holiday(dt),
            "is_weekend":          dt.weekday() >= 5,
            "hour":                dt.hour,
            "month":               dt.month,
        }

    records = list(seen.values())
    with conn.cursor() as cur:
        cur.executemany(_ROW_UPSERT_SQL, records)
    conn.commit()
    return len(records)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Bulk historical data loader")
    print("=" * 60)

    conn = psycopg2.connect(DB_DSN)
    print(f"Connected to PostgreSQL: {DB_DSN}")

    now = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Also load current month up to today
    end_load = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    current = LOAD_FROM
    total_rows = 0

    while current < end_load:
        # Calculate month boundaries
        year, month = current.year, current.month
        days_in_month = monthrange(year, month)[1]
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)

        if month == end_load.month and year == end_load.year:
            # Partial current month
            month_end = end_load
        else:
            month_end = datetime(year, month, days_in_month, 23, 59, tzinfo=timezone.utc) + timedelta(minutes=1)

        print(f"\n[{year}-{month:02d}] Fetching {month_start.strftime('%Y-%m-%d')} → {month_end.strftime('%Y-%m-%d')} ...", end=" ", flush=True)
        t0 = time.time()

        # Fetch prices
        price_df = fetch_awattar_month(month_start, month_end)
        print(f"prices:{len(price_df)}", end=" ", flush=True)

        # Fetch weather
        weather_df = fetch_openmeteo_month(month_start, month_end)
        print(f"weather:{len(weather_df)}", end=" ", flush=True)

        # Merge
        if price_df.empty and weather_df.empty:
            print("→ no data, skipping")
            # Advance to next month
            if month == 12:
                current = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                current = datetime(year, month + 1, 1, tzinfo=timezone.utc)
            continue

        # Build merged DataFrame indexed by timestamp
        if not price_df.empty:
            price_df["timestamp"] = pd.to_datetime(price_df["timestamp"]).dt.floor("h")
            price_indexed = price_df.set_index("timestamp")
        else:
            price_indexed = pd.DataFrame()

        if not weather_df.empty:
            weather_df = add_generation_proxy(weather_df)
            merged = price_indexed.join(weather_df, how="outer") if not price_indexed.empty else weather_df
        else:
            merged = price_indexed

        if not price_indexed.empty and not weather_df.empty:
            merged = price_indexed.join(weather_df, how="left")
        elif not price_indexed.empty:
            merged = price_indexed.copy()
            for col in ["temperature_c", "wind_speed_ms", "solar_radiation_wm2", "cloud_cover_pct",
                        "load_mw", "wind_onshore_mw", "wind_offshore_mw", "solar_mw"]:
                merged[col] = None

        merged = merged.sort_index()

        # Upsert
        n = upsert_month(conn, merged)
        total_rows += n
        elapsed = time.time() - t0
        print(f"→ {n} rows upserted ({elapsed:.1f}s)")

        # Advance to next month
        if month == 12:
            current = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            current = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        # Small delay to respect API rate limits
        time.sleep(0.5)

    conn.close()
    print(f"\n{'=' * 60}")
    print(f"Done. Total rows upserted: {total_rows}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
