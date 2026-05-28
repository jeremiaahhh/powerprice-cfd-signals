"""
Battery storage data client — German electricity grid.

Source priority:
  1. ENTSO-E Transparency Platform (requires ENTSOE_API_KEY env var)
     · A75 + PsrType B10 = Hydro Pumped Storage generation (discharging)
     · A75 + PsrType B14 = Battery storage where available (limited in DE)
  2. Proxy fallback (always available — derived from price/generation data)

ENTSO-E data availability for Germany (2025):
  - Pumped hydro (B10): reliable, ~30 min delay
  - Battery (B14): limited granularity in DE; most batteries < reporting threshold
  - Charging side (A75) not available via standard endpoint — only generation side

Quality scores: ENTSO-E B10 = 0.85, B14 = 0.75, proxy = 0.35
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

ENTSOE_BASE = "https://web-api.tp.entsoe.eu/api"
DE_BIDDING_ZONE = "10Y1001A1001A82H"
ENTSOE_NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"


@dataclass
class BatteryFlowPoint:
    timestamp: datetime
    charging_mw: float      # positive = absorbing from grid
    discharging_mw: float   # positive = injecting to grid
    net_flow_mw: float      # discharging - charging (positive = net generation)
    source: str
    is_proxy: bool
    data_quality_score: float


def _key(tag: str) -> str:
    return f"{{{ENTSOE_NS}}}{tag}"


async def _fetch_entsoe(
    start: datetime,
    end: datetime,
    psr_type: str,
    api_key: str,
) -> List[BatteryFlowPoint]:
    """Fetch A75 generation data for a given PsrType from ENTSO-E."""
    params = {
        "securityToken": api_key,
        "documentType": "A75",
        "processType": "A16",
        "in_Domain": DE_BIDDING_ZONE,
        "PsrType": psr_type,
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
    }
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(ENTSOE_BASE, params=params)
            if resp.status_code in (401, 403):
                logger.warning("ENTSO-E: auth failed (check ENTSOE_API_KEY)")
                return []
            if resp.status_code == 400:
                logger.debug("ENTSO-E: no %s data in range %s–%s", psr_type, start, end)
                return []
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("ENTSO-E request failed: %s", exc)
        return []

    return _parse_entsoe_xml(resp.text, psr_type)


def _parse_entsoe_xml(xml_text: str, psr_type: str) -> List[BatteryFlowPoint]:
    points: List[BatteryFlowPoint] = []
    quality = 0.85 if psr_type == "B10" else 0.75
    try:
        root = ET.fromstring(xml_text)
        for ts_el in root.findall(_key("TimeSeries")):
            period = ts_el.find(_key("Period"))
            if period is None:
                continue
            interval = period.find(_key("timeInterval"))
            if interval is None:
                continue
            start_str = interval.findtext(_key("start"), "")
            resolution = period.findtext(_key("resolution"), "PT60M")
            delta_min = 15 if resolution == "PT15M" else 60
            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            for pt in period.findall(_key("Point")):
                pos = int(pt.findtext(_key("position"), "1")) - 1
                qty_text = pt.findtext(_key("quantity"))
                if qty_text is None:
                    continue
                qty_mw = float(qty_text)
                ts = start_dt + pd.Timedelta(minutes=delta_min * pos)
                ts_hour = ts.replace(minute=0, second=0, microsecond=0)
                if ts_hour.tzinfo is None:
                    ts_hour = ts_hour.replace(tzinfo=timezone.utc)
                points.append(BatteryFlowPoint(
                    timestamp=ts_hour,
                    charging_mw=0.0,
                    discharging_mw=qty_mw,
                    net_flow_mw=qty_mw,
                    source=f"entsoe_{psr_type.lower()}",
                    is_proxy=False,
                    data_quality_score=quality,
                ))
    except ET.ParseError as exc:
        logger.warning("ENTSO-E XML parse error: %s", exc)
    return points


def _points_to_df(points: List[BatteryFlowPoint]) -> pd.DataFrame:
    if not points:
        return pd.DataFrame()
    rows = [
        {
            "timestamp": p.timestamp,
            "charging_mw": p.charging_mw,
            "discharging_mw": p.discharging_mw,
            "net_battery_flow_mw": p.net_flow_mw,
            "source": p.source,
            "is_proxy": p.is_proxy,
            "data_quality_score": p.data_quality_score,
        }
        for p in points
    ]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.floor("h")
    df = (
        df.groupby("timestamp")
        .agg({
            "charging_mw": "sum",
            "discharging_mw": "sum",
            "net_battery_flow_mw": "sum",
            "source": "first",
            "is_proxy": "first",
            "data_quality_score": "mean",
        })
        .reset_index()
    )
    return df


async def fetch_battery_flows(
    start: datetime,
    end: datetime,
    price_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Fetch battery flow data with automatic source fallback.

    Returns DataFrame columns:
        timestamp, charging_mw, discharging_mw, net_battery_flow_mw,
        source, is_proxy, data_quality_score
    """
    api_key = getattr(settings, "entsoe_api_key", "") or ""
    if api_key and api_key != "your-entsoe-api-key-here":
        # Try B10 (hydro pumped storage — main dispatchable storage in DE)
        pts = await _fetch_entsoe(start, end, "B10", api_key)
        if pts:
            logger.info("Battery: %d B10 (pumped hydro) points from ENTSO-E", len(pts))
            return _points_to_df(pts)
        # Try B14 (battery storage — limited in DE)
        pts = await _fetch_entsoe(start, end, "B14", api_key)
        if pts:
            logger.info("Battery: %d B14 (battery) points from ENTSO-E", len(pts))
            return _points_to_df(pts)

    # Proxy fallback
    if price_df is not None and not price_df.empty:
        logger.info("Battery: using proxy (no ENTSO-E data — configure ENTSOE_API_KEY for real data)")
        from app.data.storage_proxy import compute_storage_proxy
        return compute_storage_proxy(price_df)

    logger.warning("Battery: no data source available")
    return pd.DataFrame()
