"""Detects extreme intra-hour price gaps in German electricity market data."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class GapAssessment:
    max_gap_1h: float          # max absolute hourly price change in window
    gap_score: float           # 0-1 normalized (max_gap / 200)
    has_extreme_gap: bool      # gap > threshold
    gap_timestamps: List[str]  # timestamps of extreme gaps


class GapDetector:
    """Detects extreme intra-hour price movements."""

    def __init__(self, threshold_eur_mwh: float = 100.0):
        self.threshold = threshold_eur_mwh

    def detect(self, df: pd.DataFrame, window_hours: int = 12) -> GapAssessment:
        if df.empty or "price_eur_mwh" not in df.columns:
            return GapAssessment(0.0, 0.0, False, [])

        recent = df.tail(window_hours + 1).copy()
        recent["_gap"] = recent["price_eur_mwh"].diff().abs()
        extreme = recent[recent["_gap"] > self.threshold]
        max_gap = float(recent["_gap"].max()) if len(recent) > 1 else 0.0
        gap_score = min(max_gap / 200.0, 1.0)

        gap_ts = []
        if "timestamp" in extreme.columns:
            gap_ts = [str(ts)[:19] for ts in extreme["timestamp"].tolist()]

        return GapAssessment(
            max_gap_1h=round(max_gap, 2),
            gap_score=round(gap_score, 4),
            has_extreme_gap=bool(len(extreme) > 0),
            gap_timestamps=gap_ts,
        )
