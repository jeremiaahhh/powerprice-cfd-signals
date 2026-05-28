"""
Open-Meteo weather connector.

Fetches hourly weather data (temperature, wind speed, solar radiation,
cloud cover) from the free Open-Meteo API — no API key required.

API reference: https://open-meteo.com/en/docs

Default coordinates are set to Berlin (52.52°N, 13.41°E) as a representative
proxy for Germany-wide weather conditions relevant to power price modelling.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Default coordinates: Berlin, Germany
DEFAULT_LAT = 52.52
DEFAULT_LON = 13.41

# Hourly variables to request
HOURLY_VARIABLES = [
    "temperature_2m",       # °C at 2 m
    "wind_speed_10m",       # km/h at 10 m
    "shortwave_radiation",  # W/m² (global horizontal irradiance)
    "cloud_cover",          # % (0–100)
]

# HTTP settings
_REQUEST_TIMEOUT = 30.0
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 1.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_with_retry(
    client: httpx.AsyncClient,
    params: dict[str, Any],
) -> dict[str, Any]:
    """
    Perform a GET request to the Open-Meteo API with exponential-backoff retry.

    Returns the parsed JSON response on success.
    """
    backoff = _BASE_BACKOFF_S
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = await client.get(
                OPEN_METEO_URL,
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            # Open-Meteo returns HTTP 200 with an error key on bad requests
            if "error" in data and data["error"]:
                reason = data.get("reason", "Unknown Open-Meteo error")
                raise ValueError(f"Open-Meteo API error: {reason}")

            return data

        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "Open-Meteo request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            else:
                logger.error(
                    "Open-Meteo request failed after %d attempts: %s",
                    _MAX_RETRIES,
                    exc,
                )

    raise last_exc  # type: ignore[misc]


def _parse_hourly_response(data: dict[str, Any]) -> pd.DataFrame:
    """
    Convert an Open-Meteo JSON response into a UTC-indexed DataFrame.

    The API returns:
        {
          "hourly": {
            "time": ["2024-01-01T00:00", ...],
            "temperature_2m": [...],
            ...
          },
          "hourly_units": {...},
          ...
        }

    Open-Meteo timestamps are in the timezone specified by the ``timezone``
    request parameter; we always request UTC so no conversion is needed.
    """
    hourly = data.get("hourly", {})
    times_raw: list[str] = hourly.get("time", [])

    if not times_raw:
        logger.warning("Open-Meteo: empty 'hourly.time' in response")
        return pd.DataFrame()

    # Parse timestamps — Open-Meteo returns ISO 8601 without timezone when UTC
    timestamps = []
    for t in times_raw:
        try:
            dt = datetime.fromisoformat(t)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            timestamps.append(dt)
        except (ValueError, TypeError):
            timestamps.append(None)

    records: dict[str, list] = {"timestamp": timestamps}
    for var in HOURLY_VARIABLES:
        records[var] = hourly.get(var, [None] * len(timestamps))

    df = pd.DataFrame(records)
    df.dropna(subset=["timestamp"], inplace=True)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)

    # Cast all value columns to float (Open-Meteo can return int or None)
    for col in HOURLY_VARIABLES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _build_base_params(lat: float, lon: float) -> dict[str, Any]:
    """Return the common request parameters for Open-Meteo."""
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def fetch_forecast(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
) -> pd.DataFrame:
    """
    Fetch a 3-day ahead weather forecast from Open-Meteo.

    Parameters
    ----------
    lat:
        Latitude of the target location (default: Berlin 52.52°N).
    lon:
        Longitude of the target location (default: Berlin 13.41°E).

    Returns
    -------
    pd.DataFrame
        Indexed by UTC timestamp with columns:
        ``temperature_2m``, ``wind_speed_10m``, ``shortwave_radiation``,
        ``cloud_cover``.

        The index covers roughly the next 3 days at hourly resolution.
    """
    params = _build_base_params(lat, lon)
    params["forecast_days"] = 3

    logger.info(
        "Fetching Open-Meteo 3-day forecast for (lat=%.4f, lon=%.4f)", lat, lon
    )

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            data = await _get_with_retry(client, params)
        except Exception as exc:  # noqa: BLE001
            logger.error("Open-Meteo forecast fetch failed: %s", exc)
            return pd.DataFrame(columns=HOURLY_VARIABLES)

    df = _parse_hourly_response(data)
    df = df.rename(columns={
        "temperature_2m": "temperature_c",
        "wind_speed_10m": "wind_speed_ms",
        "shortwave_radiation": "solar_radiation_wm2",
        "cloud_cover": "cloud_cover_pct",
    })
    logger.info("Open-Meteo forecast: %d hourly rows", len(df))
    return df


async def fetch_historical(
    hours_back: int = 72,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
) -> pd.DataFrame:
    """
    Fetch recent historical weather observations from Open-Meteo.

    Open-Meteo provides past observations through the ``past_days`` parameter
    on the forecast endpoint; data is reanalysis-corrected near-real-time.

    Parameters
    ----------
    hours_back:
        Number of hours of history to retrieve.  Rounded up to the nearest
        whole day to match the Open-Meteo ``past_days`` granularity.
    lat:
        Latitude of the target location (default: Berlin 52.52°N).
    lon:
        Longitude of the target location (default: Berlin 13.41°E).

    Returns
    -------
    pd.DataFrame
        Indexed by UTC timestamp with columns:
        ``temperature_2m``, ``wind_speed_10m``, ``shortwave_radiation``,
        ``cloud_cover``.

        The returned window may be slightly wider than *hours_back* because
        Open-Meteo uses whole-day boundaries.
    """
    # Open-Meteo past_days must be an integer number of days
    past_days = max(1, -(-hours_back // 24))  # ceiling division

    params = _build_base_params(lat, lon)
    params["past_days"] = past_days
    # Request a tiny forecast window to avoid confusing historical with future
    params["forecast_days"] = 1

    logger.info(
        "Fetching Open-Meteo historical data: past %d days (lat=%.4f, lon=%.4f)",
        past_days,
        lat,
        lon,
    )

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            data = await _get_with_retry(client, params)
        except Exception as exc:  # noqa: BLE001
            logger.error("Open-Meteo historical fetch failed: %s", exc)
            return pd.DataFrame(columns=HOURLY_VARIABLES)

    df = _parse_hourly_response(data)
    df = df.rename(columns={
        "temperature_2m": "temperature_c",
        "wind_speed_10m": "wind_speed_ms",
        "shortwave_radiation": "solar_radiation_wm2",
        "cloud_cover": "cloud_cover_pct",
    })

    # Trim to the exact requested hours_back window
    if not df.empty and hours_back < past_days * 24:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours_back)
        df = df[df.index >= cutoff]

    logger.info("Open-Meteo historical: %d hourly rows (past %d days)", len(df), past_days)
    return df
