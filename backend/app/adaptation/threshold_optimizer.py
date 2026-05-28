"""
Signal threshold optimizer.
Analyzes shadow signal performance to suggest optimal entry thresholds.
ADVISORY ONLY — does not automatically change thresholds.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import psycopg2
import psycopg2.extras

from app.core.logging import get_logger

logger = get_logger(__name__)
_DSN = "postgresql://ppuser:pppass@localhost:5432/powerprice"


class ThresholdOptimizer:
    """
    Analyzes past shadow signals to find optimal p_rebound and net_edge thresholds.
    Returns suggestions — does not apply changes automatically.
    """

    def analyze(self, days_back: int = 90) -> Dict:
        """Return threshold analysis report."""
        try:
            conn = psycopg2.connect(_DSN)
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

                cur.execute(
                    "SELECT s.p_rebound, s.net_edge, s.action, "
                    "o.realized_rebound, o.simulated_pnl, o.outcome_status "
                    "FROM shadow_signals s "
                    "LEFT JOIN shadow_outcomes o ON o.signal_id = s.id "
                    "WHERE s.timestamp >= %s "
                    "AND s.action IN ('ENTER_LONG_REBOUND_SIGNAL', 'HIGH_CONFIDENCE_SIGNAL', 'WATCH_LONG_REBOUND') "
                    "AND o.outcome_status IS NOT NULL "
                    "ORDER BY s.timestamp DESC",
                    (cutoff,)
                )
                rows = cur.fetchall()
            finally:
                conn.close()

            if len(rows) < 20:
                return {"status": "insufficient_data", "rows": len(rows), "min_required": 20}

            p_reb_thresholds = np.arange(0.55, 0.85, 0.05)
            edge_thresholds = np.arange(20, 45, 5)

            best_pf = 0.0
            best_p_reb = 0.70
            best_edge = 30.0

            for p_thresh in p_reb_thresholds:
                for e_thresh in edge_thresholds:
                    eligible = [
                        r for r in rows
                        if (r["p_rebound"] or 0) >= p_thresh
                        and (r["net_edge"] or 0) >= e_thresh
                    ]
                    if len(eligible) < 5:
                        continue
                    profits = sum(r["simulated_pnl"] for r in eligible if r["simulated_pnl"] and r["simulated_pnl"] > 0)
                    losses = sum(abs(r["simulated_pnl"]) for r in eligible if r["simulated_pnl"] and r["simulated_pnl"] < 0)
                    pf = profits / max(losses, 0.01)
                    if pf > best_pf:
                        best_pf = pf
                        best_p_reb = float(p_thresh)
                        best_edge = float(e_thresh)

            current_win_rate = sum(1 for r in rows if r["outcome_status"] == "win") / len(rows)

            return {
                "status": "ok",
                "sample_size": len(rows),
                "days_analyzed": days_back,
                "current_win_rate": round(current_win_rate, 4),
                "optimal_p_rebound": round(best_p_reb, 2),
                "optimal_net_edge": round(best_edge, 1),
                "optimal_pf": round(best_pf, 4),
                "note": "ADVISORY ONLY — thresholds not applied automatically",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("ThresholdOptimizer.analyze failed: %s", exc)
            return {"status": "error", "error": str(exc)}
