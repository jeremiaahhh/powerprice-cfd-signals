"""GET /notifications/* – notification history and status."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter()


@router.get("/recent", summary="Recent notification events")
async def get_recent_notifications(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    try:
        from app.db.models import NotificationEvent
        stmt = select(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        return [{k: v for k, v in r.__dict__.items() if not k.startswith("_")} for r in rows]
    except Exception as exc:
        logger.exception("GET /notifications/recent failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/stats", summary="Notification statistics")
async def get_notification_stats(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        from app.db.models import NotificationEvent
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(NotificationEvent).where(NotificationEvent.created_at >= cutoff)
        rows = (await db.execute(stmt)).scalars().all()
        total = len(rows)
        sent = sum(1 for r in rows if r.status == "sent")
        failed = sum(1 for r in rows if r.status == "failed")
        by_type: Dict[str, int] = {}
        for r in rows:
            by_type[r.event_type] = by_type.get(r.event_type, 0) + 1
        last_sent = max((r.created_at for r in rows if r.status == "sent"), default=None)
        return {
            "days_analyzed": days,
            "total": total,
            "sent": sent,
            "failed": failed,
            "by_type": by_type,
            "last_sent_at": last_sent.isoformat() if last_sent else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.exception("GET /notifications/stats failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
