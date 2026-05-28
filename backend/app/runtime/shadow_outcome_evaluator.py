"""
Shadow outcome evaluator.
Periodically fills in realized prices for past shadow signals.
Evaluates: 1h, 2h, 4h, 6h outcomes.
Computes simulated PnL and win/loss status.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_DSN = "postgresql://ppuser:pppass@localhost:5432/powerprice"
_STOP_LOSS_DEFAULT = 20.0   # EUR/MWh
_TAKE_PROFIT_DEFAULT = 14.0  # EUR/MWh
_WIN_THRESHOLD = 14.0        # EUR/MWh rebound needed for a "win"


class ShadowOutcomeEvaluator:
    """
    Evaluates shadow signals after their horizon has elapsed.
    Fills in realized_price_1h, _2h, _4h and computes simulated PnL.
    Updates outcome_status: win / loss / partial / pending.

    Runs against the shadow_signals + shadow_outcomes tables.
    Uses only hourly_prices data — no look-ahead.
    """

    def evaluate_pending(self) -> int:
        """
        Find shadow signals >= 1h old with no outcome, evaluate them.
        Returns count of newly evaluated signals.
        """
        now = datetime.now(timezone.utc)
        cutoff_1h = now - timedelta(hours=1)
        evaluated = 0

        try:
            conn = psycopg2.connect(_DSN)
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

                # Find ENTER / HIGH_CONFIDENCE signals with no shadow_outcome yet
                cur.execute(
                    """
                    SELECT s.id, s.timestamp, s.action, s.current_price, s.net_edge
                    FROM shadow_signals s
                    LEFT JOIN shadow_outcomes o ON o.signal_id = s.id
                    WHERE s.timestamp <= %s
                      AND s.action IN ('ENTER_LONG_REBOUND_SIGNAL', 'HIGH_CONFIDENCE_SIGNAL')
                      AND o.id IS NULL
                    ORDER BY s.timestamp ASC
                    LIMIT 100
                    """,
                    (cutoff_1h,),
                )
                pending = cur.fetchall()

                for sig in pending:
                    sig_ts = sig["timestamp"]
                    if sig_ts.tzinfo is None:
                        sig_ts = sig_ts.replace(tzinfo=timezone.utc)
                    entry_price = sig["current_price"]
                    if entry_price is None:
                        continue

                    # Fetch realized prices at +1h, +2h, +4h
                    p1h = self._fetch_price(cur, sig_ts + timedelta(hours=1))
                    p2h = self._fetch_price(cur, sig_ts + timedelta(hours=2))
                    p4h = self._fetch_price(cur, sig_ts + timedelta(hours=4))

                    # Only evaluate if at least +4h data is available
                    if p4h is None:
                        continue

                    # Compute realized rebound (max price over horizon vs entry)
                    prices_available = [p for p in [p1h, p2h, p4h] if p is not None]
                    max_price = max(prices_available)
                    realized_rebound = max_price - entry_price

                    # Simulated PnL: enter at entry_price, exit at max price (simplified)
                    simulated_pnl = realized_rebound

                    # Stop/take-profit evaluation
                    stop = entry_price - _STOP_LOSS_DEFAULT
                    take = entry_price + _TAKE_PROFIT_DEFAULT
                    would_hit_stop = any(p is not None and p <= stop for p in prices_available)
                    would_hit_tp = any(p is not None and p >= take for p in prices_available)

                    # Outcome status
                    if realized_rebound >= _WIN_THRESHOLD:
                        outcome_status = "win"
                    elif realized_rebound < -_STOP_LOSS_DEFAULT:
                        outcome_status = "loss"
                    else:
                        outcome_status = "partial"

                    cur.execute(
                        """
                        INSERT INTO shadow_outcomes
                        (signal_id, evaluated_at, realized_price_1h, realized_price_2h,
                         realized_price_4h, realized_rebound, simulated_pnl,
                         would_hit_stop, would_hit_take_profit, outcome_status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            sig["id"], now, p1h, p2h, p4h,
                            round(realized_rebound, 2),
                            round(simulated_pnl, 2),
                            would_hit_stop, would_hit_tp,
                            outcome_status, now,
                        ),
                    )
                    evaluated += 1

                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.error("ShadowOutcomeEvaluator.evaluate_pending failed: %s", exc)

        if evaluated > 0:
            logger.info("Shadow outcomes evaluated: %d new records", evaluated)
        return evaluated

    def _fetch_price(self, cur, ts: datetime) -> Optional[float]:
        try:
            ts_naive = ts.replace(tzinfo=None)
            cur.execute(
                "SELECT price_eur_mwh FROM hourly_prices WHERE timestamp = %s LIMIT 1",
                (ts_naive,),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def compute_rolling_performance(self, window: int = 30) -> dict:
        """Compute rolling PF and win rate over the last N completed shadow outcomes."""
        try:
            conn = psycopg2.connect(_DSN)
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute(
                    """
                    SELECT o.simulated_pnl, o.outcome_status
                    FROM shadow_outcomes o
                    JOIN shadow_signals s ON s.id = o.signal_id
                    WHERE o.outcome_status IN ('win', 'loss', 'partial')
                    ORDER BY o.evaluated_at DESC
                    LIMIT %s
                    """,
                    (window,),
                )
                rows = cur.fetchall()
            finally:
                conn.close()

            if not rows:
                return {"rolling_pf": None, "rolling_win_rate": None, "sample_size": 0}

            wins = sum(1 for r in rows if r["outcome_status"] == "win")
            profits = sum(r["simulated_pnl"] for r in rows if r["simulated_pnl"] and r["simulated_pnl"] > 0)
            losses = sum(abs(r["simulated_pnl"]) for r in rows if r["simulated_pnl"] and r["simulated_pnl"] < 0)
            pf = profits / losses if losses > 0 else None
            win_rate = wins / len(rows)

            return {
                "rolling_pf": round(pf, 4) if pf else None,
                "rolling_win_rate": round(win_rate, 4),
                "sample_size": len(rows),
            }
        except Exception as exc:
            logger.error("compute_rolling_performance failed: %s", exc)
            return {"rolling_pf": None, "rolling_win_rate": None, "sample_size": 0, "error": str(exc)}
