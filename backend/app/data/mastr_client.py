"""
Marktstammdatenregister (MaStR) client — installed battery capacity for Germany.

MaStR is the official German energy installation registry. Battery storage
(Stromspeicher) capacity data is extracted and cached for 24 h, since it
changes on timescales of weeks, not minutes.

Known capacity milestones (source: MaStR / Fraunhofer ISE / Bundesnetzagentur):
Used for interpolation when the live API is unavailable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

MASTR_BASE = "https://www.marktstammdatenregister.de/MaStR"

# (year, month, power_mw, capacity_mwh) — from public MaStR statistics
_MILESTONES: list[Tuple[int, int, float, float]] = [
    (2024, 1,   7_500,  15_000),
    (2024, 6,   9_000,  18_000),
    (2024, 12, 10_500,  21_000),
    (2025, 1,  11_500,  23_000),
    (2025, 6,  13_500,  27_000),
    (2025, 12, 15_000,  30_000),
    (2026, 1,  16_000,  32_000),
    (2026, 6,  17_500,  35_000),
]

_cache: Optional[Tuple[datetime, "CapacityEstimate"]] = None
_CACHE_TTL_S = 86_400  # 24 h


@dataclass
class CapacityEstimate:
    power_mw: float
    capacity_mwh: float
    source: str   # "mastr_api" | "mastr_milestone"
    as_of: datetime
    data_quality_score: float


def _interpolate(as_of: datetime) -> CapacityEstimate:
    y, m = as_of.year, as_of.month
    before: Optional[Tuple] = None
    after: Optional[Tuple] = None
    for row in _MILESTONES:
        ry, rm = row[0], row[1]
        if (ry, rm) <= (y, m):
            before = row
        elif after is None:
            after = row

    if before is None:
        ry, rm, pw, cap = _MILESTONES[0]
        return CapacityEstimate(pw, cap, "mastr_milestone", as_of, 0.55)

    if after is None:
        ry, rm, pw, cap = before
        months_past = (y - ry) * 12 + (m - rm)
        growth_mw = months_past * 250.0   # ~250 MW / month growth rate
        return CapacityEstimate(
            round(pw + growth_mw, 0),
            round((pw + growth_mw) * 2.0, 0),
            "mastr_milestone",
            as_of,
            0.55,
        )

    y0, m0, pw0, cap0 = before
    y1, m1, pw1, cap1 = after
    total = (y1 - y0) * 12 + (m1 - m0)
    elapsed = (y - y0) * 12 + (m - m0)
    t = elapsed / total if total > 0 else 0.5
    return CapacityEstimate(
        power_mw=round(pw0 + t * (pw1 - pw0), 0),
        capacity_mwh=round(cap0 + t * (cap1 - cap0), 0),
        source="mastr_milestone",
        as_of=as_of,
        data_quality_score=0.70,
    )


async def fetch_capacity(as_of: Optional[datetime] = None) -> CapacityEstimate:
    """
    Return current installed battery storage capacity estimate for Germany.

    Tries MaStR REST API first; falls back to milestone interpolation.
    Result is cached for 24 h.
    """
    global _cache
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    if _cache is not None:
        cached_ts, est = _cache
        if (as_of - cached_ts).total_seconds() < _CACHE_TTL_S:
            return est

    # Try MaStR public API
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                f"{MASTR_BASE}/Einheit/EinheitJson/GetVerkehr",
                params={"unitTypes": "8", "states": "35", "regions": "0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                total_kw = data.get("TotalPower") or data.get("totalPower") or 0
                if float(total_kw) > 0:
                    pw = round(float(total_kw) / 1_000.0, 0)  # kW → MW
                    cap = round(pw * 2.0, 0)                   # ~2 h average duration
                    est = CapacityEstimate(pw, cap, "mastr_api", as_of, 0.85)
                    _cache = (as_of, est)
                    logger.info("MaStR: %.0f MW / %.0f MWh installed battery storage", pw, cap)
                    return est
    except Exception as exc:
        logger.debug("MaStR API unavailable (%s) — using milestone interpolation", exc)

    est = _interpolate(as_of)
    _cache = (as_of, est)
    logger.info(
        "MaStR: interpolated %.0f MW / %.0f MWh (source=%s)",
        est.power_mw, est.capacity_mwh, est.source,
    )
    return est
