"""Regime-based entry blocker — prevents entries in hostile market regimes."""
from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger(__name__)

_HARD_BLOCKED_REGIMES = {"STRESS"}
_SOFT_BLOCKED_REGIMES = {"STORAGE_SATURATED", "BATTERY_DAMPENED_REBOUND"}


class RegimeBlocker:
    """Blocks entry based on current market regime + tail risk interaction."""

    def should_block(
        self,
        regime_value: str,
        tail_risk_score: float = 0.0,
    ) -> Tuple[bool, str, str]:
        """
        Returns (is_blocked, signal_action_name, detail).
        signal_action_name: "EXTREME_VOLATILITY_BLOCKED" | "TAIL_RISK_BLOCKED" | ""
        """
        if regime_value in _HARD_BLOCKED_REGIMES:
            return (
                True,
                "EXTREME_VOLATILITY_BLOCKED",
                f"STRESS regime blocks all entries — extreme market conditions",
            )
        if regime_value in _SOFT_BLOCKED_REGIMES and tail_risk_score > 0.50:
            return (
                True,
                "TAIL_RISK_BLOCKED",
                f"Regime {regime_value} + elevated tail risk "
                f"({tail_risk_score:.2f}) — entry suppressed",
            )
        return False, "", "ok"
