"""
Battery service — orchestrates data fetching, caching, and feature computation.

Usage (async context):
    service = BatteryService()
    features_df = await service.get_battery_features(hourly_df)
    capacity    = await service.get_installed_capacity()
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

import pandas as pd

from app.data.battery_client import fetch_battery_flows
from app.data.mastr_client import CapacityEstimate, fetch_capacity
from app.data.storage_proxy import compute_storage_proxy
from app.features.battery_features import BatteryFeatureBuilder

logger = logging.getLogger(__name__)

_capacity_cache: Optional[Tuple[datetime, CapacityEstimate]] = None
_CACHE_TTL_S = 86_400  # 24 h


class BatteryService:
    """Orchestrates battery capacity, flow data, and feature computation."""

    # ------------------------------------------------------------------
    # Capacity
    # ------------------------------------------------------------------

    async def get_installed_capacity(self) -> dict:
        """Return installed battery capacity with 24-h in-process cache."""
        global _capacity_cache
        now = datetime.now(timezone.utc)
        if _capacity_cache is not None:
            ts, est = _capacity_cache
            if (now - ts).total_seconds() < _CACHE_TTL_S:
                return self._capacity_to_dict(est)
        est = await fetch_capacity(as_of=now)
        _capacity_cache = (now, est)
        return self._capacity_to_dict(est)

    @staticmethod
    def _capacity_to_dict(est: CapacityEstimate) -> dict:
        return {
            "power_mw":           est.power_mw,
            "capacity_mwh":       est.capacity_mwh,
            "source":             est.source,
            "as_of":              est.as_of.isoformat(),
            "data_quality_score": est.data_quality_score,
        }

    # ------------------------------------------------------------------
    # Battery features
    # ------------------------------------------------------------------

    async def get_battery_features(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Compute battery features for a HourlyPrice DataFrame.

        1. Fetch installed capacity
        2. Fetch real battery flows (ENTSO-E) or fall back to proxy
        3. Build BatteryFeatureBuilder features
        """
        if df.empty:
            return df

        capacity = await self.get_installed_capacity()
        ts_col   = pd.to_datetime(df["timestamp"])
        start    = ts_col.min().to_pydatetime()
        end      = ts_col.max().to_pydatetime()

        flow_df = await fetch_battery_flows(start=start, end=end, price_df=df)

        builder = BatteryFeatureBuilder(
            installed_power_mw=capacity["power_mw"],
            installed_capacity_mwh=capacity["capacity_mwh"],
        )
        return builder.build_features(df, battery_flow_df=flow_df if not flow_df.empty else None)

    # ------------------------------------------------------------------
    # Proxy features (no ENTSO-E, always available)
    # ------------------------------------------------------------------

    async def get_proxy_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute proxy features from price/generation only."""
        capacity = await self.get_installed_capacity()
        return compute_storage_proxy(
            df,
            installed_power_mw=capacity["power_mw"],
            installed_capacity_mwh=capacity["capacity_mwh"],
        )

    # ------------------------------------------------------------------
    # Data quality report
    # ------------------------------------------------------------------

    async def get_data_quality_report(self, df: pd.DataFrame) -> dict:
        """Summarise battery data source quality."""
        from app.core.config import settings
        api_key = getattr(settings, "entsoe_api_key", "") or ""
        has_key = bool(api_key) and api_key != "your-entsoe-api-key-here"
        capacity = await self.get_installed_capacity()
        batt_cols = [c for c in df.columns if "battery" in c or "storage" in c]
        non_null = {
            col: round(float(df[col].notna().mean() * 100), 1)
            for col in batt_cols
            if col in df.columns
        }
        return {
            "status":               "ok",
            "entsoe_key_configured": has_key,
            "data_source":          "entsoe_b10" if has_key else "proxy",
            "is_proxy":             not has_key,
            "data_quality_score":   0.85 if has_key else 0.35,
            "installed_capacity":   capacity,
            "battery_columns":      len(batt_cols),
            "non_null_pct":         non_null,
            "note": (
                "Real pumped-storage data via ENTSO-E B10."
                if has_key else
                "Using proxy derived from price + generation data. "
                "Set ENTSOE_API_KEY in .env for real-time pumped-storage data."
            ),
        }
