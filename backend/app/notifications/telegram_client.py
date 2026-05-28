"""Async Telegram Bot API client. Fire-and-forget with error capture."""
from __future__ import annotations

import hashlib
import html
import json
import os
from datetime import datetime, timezone
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    """
    Thin async wrapper around Telegram Bot API sendMessage.
    Uses httpx async if available, falls back to urllib (sync wrapped in executor).
    SIGNAL ONLY - never sends order execution commands.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self._url = TELEGRAM_API_BASE.format(token=bot_token, method="sendMessage")

    async def send_html(self, text: str) -> bool:
        """Send an HTML-formatted message. Returns True on success."""
        if not self.bot_token or not self.chat_id:
            logger.debug("Telegram not configured — skipping send")
            return False
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(self._url, json=payload)
                    if resp.status_code == 200:
                        return True
                    logger.warning("Telegram API error %d: %s", resp.status_code, resp.text[:200])
                    return False
            except ImportError:
                # Fallback to sync urllib in executor
                import asyncio
                import urllib.request
                def _send():
                    data = json.dumps(payload).encode()
                    req = urllib.request.Request(
                        self._url,
                        data=data,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return resp.status == 200
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _send)
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    async def test_connection(self) -> bool:
        """Send a test ping message. Returns True if successful."""
        return await self.send_html(
            "<b>PowerPrice Signal Platform</b>\n"
            "Telegram-Verbindung erfolgreich eingerichtet.\n"
            "<i>Signal only. Keine Order ausgeführt.</i>"
        )
