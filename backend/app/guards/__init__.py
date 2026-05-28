"""
Signal guards: pre-entry checks that block trades on bad data conditions.
Each guard returns (is_ok: bool, reason: str).
"""

from __future__ import annotations
import pandas as pd
import numpy as np

def gap_guard(df: pd.DataFrame, max_gap_hours: float = 2.0, lookback_rows: int = 6) -> tuple[bool, str]:
    """Block if any of the last `lookback_rows` rows has a timestamp gap > max_gap_hours."""
    if df.empty or "timestamp" not in df.columns or len(df) < 2:
        return True, "ok"
    recent = df.sort_values("timestamp").tail(lookback_rows + 1)
    ts = pd.to_datetime(recent["timestamp"], utc=True)
    gaps_h = ts.diff().dt.total_seconds().dropna() / 3600.0
    max_gap = float(gaps_h.max()) if len(gaps_h) > 0 else 0.0
    if max_gap > max_gap_hours:
        return False, f"Data gap of {max_gap:.1f}h in last {lookback_rows} rows — entry suppressed"
    return True, "ok"

def volatility_guard(df: pd.DataFrame, max_vol_eur_mwh: float = 100.0, window: int = 24) -> tuple[bool, str]:
    """Block if 24h price std > max_vol_eur_mwh (spread would be extreme)."""
    if df.empty or "price_eur_mwh" not in df.columns:
        return True, "ok"
    prices = df["price_eur_mwh"].dropna().tail(window)
    if len(prices) < 6:
        return True, "ok"
    vol = float(prices.std())
    if vol > max_vol_eur_mwh:
        return False, f"24h price volatility {vol:.1f} EUR/MWh exceeds {max_vol_eur_mwh:.0f} — spread extreme"
    return True, "ok"

def spread_guard(price_volatility_24h: float | None, max_spread_factor: float = 3.0, base_spread: float = 5.0) -> tuple[bool, str]:
    """Block if implied spread (vol-adjusted) exceeds max_spread_factor × base_spread."""
    if price_volatility_24h is None or not np.isfinite(price_volatility_24h):
        return True, "ok"
    # Simple proxy: spread widens proportionally to vol above 30 EUR/MWh
    if price_volatility_24h > 30.0:
        implied = base_spread * (1.0 + (price_volatility_24h - 30.0) / 30.0)
        if implied > base_spread * max_spread_factor:
            return False, f"Implied spread {implied:.1f} EUR/MWh too wide (vol={price_volatility_24h:.1f})"
    return True, "ok"

def data_quality_guard(df: pd.DataFrame, required_cols: list[str] | None = None, max_age_minutes: float = 90.0) -> tuple[bool, str]:
    """Block if required columns are missing/all-NaN or data is stale."""
    if df.empty:
        return False, "No market data available"
    if required_cols:
        for col in required_cols:
            if col not in df.columns or df[col].dropna().empty:
                return False, f"Required column '{col}' is missing or all-NaN"
    # Check data freshness
    if "timestamp" in df.columns:
        from datetime import datetime, timezone
        latest_ts = pd.to_datetime(df["timestamp"], utc=True).max()
        age_min = (datetime.now(timezone.utc) - latest_ts).total_seconds() / 60.0
        if age_min > max_age_minutes:
            return False, f"Market data is stale ({age_min:.0f} minutes old)"
    return True, "ok"
