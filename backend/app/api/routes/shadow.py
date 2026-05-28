from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.db.models import HourlyPrice

logger = get_logger(__name__)
router = APIRouter()

_WIN_THRESHOLD = 14.0  # EUR/MWh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shadow_to_dict(row: Any) -> Dict[str, Any]:
    return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}


async def _lookup_price_at(
    db: AsyncSession,
    ts: datetime,
) -> Optional[float]:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    stmt = (
        select(HourlyPrice.price_eur_mwh)
        .where(HourlyPrice.timestamp == ts)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/live-signals", summary="Recent shadow signal records")
async def get_live_signals(
    limit: int = Query(default=50, ge=1, le=500, description="Number of records to return"),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    try:
        from app.db.models import ShadowSignal
    except ImportError:
        logger.warning("ShadowSignal model not found")
        return []

    try:
        stmt = (
            select(ShadowSignal)
            .order_by(ShadowSignal.timestamp.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        logger.info("GET /shadow/live-signals: returning %d rows", len(rows))
        return [_shadow_to_dict(r) for r in rows]
    except Exception as exc:
        logger.exception("GET /shadow/live-signals failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Failed to fetch shadow signals: {exc}")


@router.get("/performance", summary="Shadow signal predicted vs realized stats")
async def get_shadow_performance(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        from app.db.models import ShadowSignal
    except ImportError:
        return {"status": "unavailable", "message": "ShadowSignal model not configured"}

    try:
        stmt = (
            select(ShadowSignal)
            .where(ShadowSignal.realized_price_6h.isnot(None))
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return {
                "status": "no_realized_data",
                "message": "No shadow signals with realized prices yet — wait 6h after first signals are generated",
            }

        prediction_errors: List[float] = []
        abs_errors: List[float] = []
        enter_rebonds: List[float] = []
        signal_counts: Dict[str, int] = defaultdict(int)

        for row in rows:
            action = getattr(row, "action", None)
            if action:
                signal_counts[action] += 1

            predicted = getattr(row, "predicted_price", None)
            realized_6h = getattr(row, "realized_price_6h", None)
            current_price = getattr(row, "current_price", None)

            if predicted is not None and realized_6h is not None:
                err = predicted - realized_6h
                prediction_errors.append(err)
                abs_errors.append(abs(err))

            if action in {"ENTER_LONG_REBOUND_SIGNAL", "HIGH_CONFIDENCE_SIGNAL"}:
                if current_price is not None and realized_6h is not None:
                    enter_rebonds.append(realized_6h - current_price)

        mean_prediction_error = round(float(np.mean(prediction_errors)), 4) if prediction_errors else None
        mean_abs_error = round(float(np.mean(abs_errors)), 4) if abs_errors else None
        win_rate: Optional[float] = None
        if enter_rebonds:
            win_rate = round(sum(1 for r in enter_rebonds if r > _WIN_THRESHOLD) / len(enter_rebonds), 4)

        logger.info(
            "GET /shadow/performance: %d realized rows, MAE=%.2f, win_rate=%s",
            len(rows),
            mean_abs_error or 0,
            win_rate,
        )
        return {
            "status": "ok",
            "total_realized": len(rows),
            "mean_prediction_error": mean_prediction_error,
            "mean_abs_error": mean_abs_error,
            "win_rate": win_rate,
            "signal_counts": dict(signal_counts),
        }

    except Exception as exc:
        logger.exception("GET /shadow/performance failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Failed to compute shadow performance: {exc}")


@router.post("/backfill", summary="Fill realized prices for past shadow signals")
async def backfill_shadow_signals(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        from app.db.models import ShadowSignal
    except ImportError:
        return {"filled": 0, "message": "ShadowSignal model not configured"}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=7)

    try:
        stmt = (
            select(ShadowSignal)
            .where(
                ShadowSignal.realized_price_6h.is_(None),
                ShadowSignal.timestamp < cutoff,
            )
            .order_by(ShadowSignal.timestamp.asc())
            .limit(100)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        filled = 0
        for row in rows:
            ts = row.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            p1h = await _lookup_price_at(db, ts + timedelta(hours=1))
            p4h = await _lookup_price_at(db, ts + timedelta(hours=4))
            p6h = await _lookup_price_at(db, ts + timedelta(hours=6))

            if p6h is None:
                continue

            row.realized_price_1h = p1h
            row.realized_price_4h = p4h
            row.realized_price_6h = p6h

            current_price = getattr(row, "current_price", None)
            if current_price is not None:
                row.realized_rebound = p6h - current_price

            predicted = getattr(row, "predicted_price", None)
            if predicted is not None:
                row.prediction_error = predicted - p6h

            filled += 1

        if filled > 0:
            await db.commit()

        logger.info("POST /shadow/backfill: filled %d rows", filled)
        return {"filled": filled}

    except Exception as exc:
        logger.exception("POST /shadow/backfill failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Backfill failed: {exc}")
