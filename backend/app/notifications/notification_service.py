"""
Notification service: orchestrates Telegram sends with deduplication.
Uses in-memory TTL cache + DB persistence for the notification_events table.
SIGNAL ONLY - never sends order execution commands.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import psycopg2
import psycopg2.extras

from app.core.config import settings
from app.core.logging import get_logger
from .telegram_client import TelegramClient
from .message_templates import (
    format_signal, format_error_alert, format_daily_summary,
    format_retrain_report, format_drift_alert
)

logger = get_logger(__name__)

# DSN for sync dedup DB access
_DSN = "postgresql://ppuser:pppass@localhost:5432/powerprice"


class NotificationService:
    """
    Manages outbound notifications with deduplication.

    Deduplication: an in-memory dict maps fingerprint→expiry_time.
    Also persists to notification_events table.
    SIGNAL ONLY.
    """

    def __init__(self) -> None:
        self._client: Optional[TelegramClient] = None
        self._dedup_cache: Dict[str, float] = {}  # fingerprint → expiry unix ts
        self._dedup_ttl_s: int = settings.signal_dedup_minutes * 60
        self._enabled: bool = settings.telegram_enabled

        if self._enabled and settings.telegram_bot_token:
            self._client = TelegramClient(
                settings.telegram_bot_token, settings.telegram_chat_id
            )

    def _make_fingerprint(self, event_type: str, key: str) -> str:
        raw = f"{event_type}:{key}:{int(time.time() // self._dedup_ttl_s)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _is_duplicate(self, fingerprint: str) -> bool:
        now = time.time()
        # Clean expired entries
        self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if v > now}
        return fingerprint in self._dedup_cache

    def _mark_sent(self, fingerprint: str) -> None:
        self._dedup_cache[fingerprint] = time.time() + self._dedup_ttl_s

    def _persist_event(self, channel: str, event_type: str, fingerprint: str,
                       payload: dict, status: str = "sent", error: Optional[str] = None) -> None:
        """Persist notification event to DB (best-effort, fire-and-forget)."""
        try:
            conn = psycopg2.connect(_DSN)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO notification_events
                           (created_at, channel, event_type, fingerprint, payload, status, error_message)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (datetime.now(timezone.utc), channel, event_type, fingerprint,
                         json.dumps(payload), status, error)
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.debug("Failed to persist notification event: %s", exc)

    async def send_signal(self, signal: Dict[str, Any]) -> bool:
        """Send a signal notification if it meets the minimum level and is not a duplicate."""
        if not self._enabled or self._client is None:
            return False

        action = signal.get("action", "NO_TRADE")

        # Apply min signal level filter
        level_order = ["WATCH", "ENTER", "HIGH_CONFIDENCE"]
        min_level = settings.telegram_min_signal_level.upper()
        action_level = (
            "HIGH_CONFIDENCE" if action == "HIGH_CONFIDENCE_SIGNAL"
            else "ENTER" if action == "ENTER_LONG_REBOUND_SIGNAL"
            else "WATCH" if action == "WATCH_LONG_REBOUND"
            else None
        )

        # Handle blocked signals
        if action in ("TAIL_RISK_BLOCKED", "GAP_RISK_BLOCKED", "EXTREME_VOLATILITY_BLOCKED"):
            if not settings.telegram_send_blocked_signals:
                return False
            action_level = "WATCH"
        elif action in ("NO_TRADE", "DATA_QUALITY_BLOCKED", "RISK_BLOCKED"):
            return False  # Never send these

        if action_level is None:
            return False

        try:
            if level_order.index(action_level) < level_order.index(min_level):
                return False
        except ValueError:
            return False

        # Dedup: use action + approximate price bucket
        price = signal.get("current_price") or 0.0
        price_bucket = int(price // 5) * 5  # 5 EUR/MWh buckets
        fp = self._make_fingerprint(f"signal:{action}", f"{price_bucket}")
        if self._is_duplicate(fp):
            logger.debug("Signal notification deduplicated: %s", action)
            return False

        text = format_signal(signal)
        ok = await self._client.send_html(text)
        status = "sent" if ok else "failed"
        self._mark_sent(fp)
        self._persist_event("telegram", "signal", fp, signal, status)
        if ok:
            logger.info("Telegram signal sent: %s", action)
        return ok

    async def send_error_alert(self, error: str, context: Optional[Dict] = None) -> bool:
        """Send an error alert. Always sent (no dedup for errors)."""
        if not self._enabled or self._client is None:
            return False
        fp = self._make_fingerprint("error", error[:50])
        if self._is_duplicate(fp):
            return False
        text = format_error_alert(error, context)
        ok = await self._client.send_html(text)
        self._mark_sent(fp)
        self._persist_event("telegram", "error", fp, {"error": error}, "sent" if ok else "failed")
        return ok

    async def send_daily_summary(self, summary: Dict[str, Any]) -> bool:
        """Send daily performance summary. Deduplicated by day."""
        if not self._enabled or self._client is None:
            return False
        if not settings.telegram_send_daily_summary:
            return False
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        fp = self._make_fingerprint("daily_summary", today)
        if self._is_duplicate(fp):
            return False
        text = format_daily_summary(summary)
        ok = await self._client.send_html(text)
        self._mark_sent(fp)
        self._persist_event("telegram", "summary", fp, summary, "sent" if ok else "failed")
        return ok

    async def send_retrain_report(self, report: Dict[str, Any]) -> bool:
        """Send a model retraining report."""
        if not self._enabled or self._client is None:
            return False
        fp = self._make_fingerprint("retrain", report.get("model", "unknown"))
        if self._is_duplicate(fp):
            return False
        text = format_retrain_report(report)
        ok = await self._client.send_html(text)
        self._mark_sent(fp)
        self._persist_event("telegram", "retrain", fp, report, "sent" if ok else "failed")
        return ok

    async def send_drift_alert(self, report: Dict[str, Any]) -> bool:
        """Send a drift detection alert."""
        if not self._enabled or self._client is None:
            return False
        drift_key = ":".join(sorted(report.get("drift_types", [])))
        fp = self._make_fingerprint("drift", drift_key)
        if self._is_duplicate(fp):
            return False
        text = format_drift_alert(report)
        ok = await self._client.send_html(text)
        self._mark_sent(fp)
        self._persist_event("telegram", "drift", fp, report, "sent" if ok else "failed")
        return ok
