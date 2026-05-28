"""Volatility guard — classifies price volatility regime."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class VolatilityAssessment:
    vol_1h: Optional[float]
    vol_6h: float
    vol_24h: float
    vol_spike_ratio: float    # vol_24h / rolling_30d_avg (1.0 if insufficient data)
    regime: str               # "NORMAL" | "ELEVATED" | "EXTREME"
    is_blocked: bool
    detail: str


class VolatilityGuard:
    """Classifies current volatility regime."""

    def __init__(
        self,
        extreme_threshold: float = 150.0,
        elevated_threshold: float = 80.0,
        spike_multiplier: float = 2.5,
    ):
        self.extreme_threshold = extreme_threshold
        self.elevated_threshold = elevated_threshold
        self.spike_multiplier = spike_multiplier

    def assess(self, df: pd.DataFrame) -> VolatilityAssessment:
        if df.empty or "price_eur_mwh" not in df.columns:
            return VolatilityAssessment(None, 0.0, 0.0, 1.0, "NORMAL", False, "no data")

        prices = df["price_eur_mwh"].dropna()

        vol_24h = float(prices.tail(24).std()) if len(prices) >= 2 else 0.0
        vol_6h = float(prices.tail(6).std()) if len(prices) >= 2 else 0.0
        vol_1h = float(prices.tail(2).std()) if len(prices) >= 2 else None

        # Rolling 30d avg vol for spike ratio
        spike_ratio = 1.0
        if len(prices) >= 720:
            rolling_vol = prices.rolling(24).std().dropna()
            avg_30d = float(rolling_vol.tail(720).mean())
            if avg_30d > 0:
                spike_ratio = round(vol_24h / avg_30d, 2)

        # Classify regime
        if vol_24h > self.extreme_threshold or spike_ratio > self.spike_multiplier:
            regime = "EXTREME"
            is_blocked = True
            detail = (
                f"EXTREME volatility: vol_24h={vol_24h:.1f} EUR/MWh "
                f"(threshold {self.extreme_threshold:.0f}) | "
                f"spike_ratio={spike_ratio:.1f}x (threshold {self.spike_multiplier:.1f}x)"
            )
        elif vol_24h > self.elevated_threshold:
            regime = "ELEVATED"
            is_blocked = False
            detail = f"ELEVATED volatility: vol_24h={vol_24h:.1f} EUR/MWh"
        else:
            regime = "NORMAL"
            is_blocked = False
            detail = f"Normal volatility: vol_24h={vol_24h:.1f} EUR/MWh"

        return VolatilityAssessment(
            vol_1h=round(vol_1h, 2) if vol_1h is not None else None,
            vol_6h=round(vol_6h, 2),
            vol_24h=round(vol_24h, 2),
            vol_spike_ratio=spike_ratio,
            regime=regime,
            is_blocked=is_blocked,
            detail=detail,
        )
