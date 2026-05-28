"""
ENTSO-E Transparency Platform connector.

Fetches Day-Ahead electricity prices and actual load/generation data for the
DE-LU bidding zone (EIC: 10Y1001A1001A82H) via the ENTSO-E REST API.

API documentation: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html

XML namespaces vary by document type; this module handles the most common ones
used in Publication_MarketDocument and GL_MarketDocument responses.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Optional
import re

import httpx
import pandas as pd

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTSOE_BASE_URL = "https://web-api.tp.entsoe.eu/api"

# EIC (Energy Identification Code) for DE-LU bidding zone
DE_LU_BIDDING_ZONE = "10Y1001A1001A82H"

# ENTSO-E document type / process codes
DOC_TYPE_PRICES = "A44"          # Price document
DOC_TYPE_LOAD = "A65"            # System total load
PROCESS_TYPE_DAY_AHEAD = "A01"
PROCESS_TYPE_REALISED = "A16"

# XML namespaces encountered in ENTSO-E responses
_NS_PUBLICATION = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
_NS_GL = "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"
_NS_UNAVAILABILITY = "urn:iec62325.351:tc57wg16:451-7:unavailabilitydocument:5:1"

# The ENTSO-E API timestamp format
_TS_FORMAT = "%Y%m%d%H%M"

# HTTP request settings
_REQUEST_TIMEOUT = 45.0
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 2.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_ts(dt: datetime) -> str:
    """Format a datetime to the ENTSO-E API timestamp string (UTC)."""
    utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return utc_dt.strftime(_TS_FORMAT)


def _parse_entsoe_datetime(raw: str) -> datetime:
    """
    Parse an ISO-8601-like datetime string from ENTSO-E XML into a UTC datetime.

    ENTSO-E uses formats such as:
      - "2024-01-15T23:00Z"
      - "2024-01-15T23:00+00:00"
    """
    raw = raw.strip()
    # Normalise 'Z' suffix to '+00:00' for fromisoformat compatibility
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    return dt.astimezone(timezone.utc)


def _find_text(element: ET.Element, tag: str, namespaces: dict[str, str]) -> str | None:
    """Return the text of the first matching child element, or None."""
    found = element.find(tag, namespaces)
    return found.text.strip() if found is not None and found.text else None


async def _get_with_retry(
    client: httpx.AsyncClient,
    params: dict,
) -> str:
    """
    Perform a GET request to the ENTSO-E API with exponential-backoff retry.

    Returns the raw response text on success.
    """
    backoff = _BASE_BACKOFF_S
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = await client.get(
                ENTSOE_BASE_URL,
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            # ENTSO-E returns 200 even for error XML sometimes; check content type
            if response.status_code == 200:
                return response.text
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "ENTSO-E request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            else:
                logger.error(
                    "ENTSO-E request failed after %d attempts: %s",
                    _MAX_RETRIES,
                    exc,
                )

    raise last_exc  # type: ignore[misc]


def _detect_namespace(xml_text: str) -> str | None:
    """
    Detect the XML namespace from the root element of the document.

    ENTSO-E uses different namespaces depending on the document type.
    """
    match = re.search(r'xmlns="([^"]+)"', xml_text[:500])
    return match.group(1) if match else None


def _is_error_response(xml_text: str) -> tuple[bool, str]:
    """
    Check whether the ENTSO-E response is an Acknowledgement_MarketDocument
    containing an error reason.  Returns (is_error, reason_text).
    """
    if "Acknowledgement_MarketDocument" in xml_text:
        try:
            root = ET.fromstring(xml_text)
            ns = {"a": _detect_namespace(xml_text) or ""}
            reason = root.find("./a:Reason/a:text", ns)
            code_el = root.find("./a:Reason/a:code", ns)
            reason_text = (reason.text if reason is not None else "Unknown error")
            code_text = (code_el.text if code_el is not None else "?")
            return True, f"code={code_text}: {reason_text}"
        except ET.ParseError:
            return True, "Unparseable error response"
    return False, ""


def _parse_price_document(xml_text: str) -> pd.DataFrame:
    """
    Parse a Publication_MarketDocument (day-ahead prices) XML response.

    Returns a DataFrame indexed by UTC timestamp with a ``price_eur_mwh`` column.
    """
    ns_uri = _detect_namespace(xml_text)
    if ns_uri is None:
        logger.error("ENTSO-E price response: cannot detect XML namespace")
        return pd.DataFrame()

    ns = {"p": ns_uri}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("ENTSO-E price response: XML parse error: %s", exc)
        return pd.DataFrame()

    records: list[dict] = []

    for ts_el in root.findall(".//p:TimeSeries", ns):
        # Resolution period start / end
        period = ts_el.find("p:Period", ns)
        if period is None:
            continue

        time_interval = period.find("p:timeInterval", ns)
        if time_interval is None:
            continue

        start_raw = _find_text(time_interval, "p:start", ns)
        if start_raw is None:
            continue
        try:
            period_start = _parse_entsoe_datetime(start_raw)
        except (ValueError, TypeError):
            continue

        resolution_raw = _find_text(period, "p:resolution", ns) or "PT60M"
        # Parse ISO 8601 duration (simple cases: PT15M, PT30M, PT60M, P1D)
        res_match = re.match(r"PT(\d+)M", resolution_raw)
        if res_match:
            resolution_minutes = int(res_match.group(1))
        elif resolution_raw == "P1D":
            resolution_minutes = 1440
        else:
            resolution_minutes = 60  # fallback

        for point in period.findall("p:Point", ns):
            pos_text = _find_text(point, "p:position", ns)
            price_text = _find_text(point, "p:price.amount", ns)
            if pos_text is None or price_text is None:
                continue
            try:
                position = int(pos_text)
                price = float(price_text)
            except (ValueError, TypeError):
                continue

            ts = period_start + timedelta(minutes=resolution_minutes * (position - 1))
            records.append({"timestamp": ts, "price_eur_mwh": price})

    if not records:
        logger.warning("ENTSO-E price document: no data points parsed")
        return pd.DataFrame()

    df = (
        pd.DataFrame(records)
        .drop_duplicates(subset=["timestamp"])
        .set_index("timestamp")
        .sort_index()
    )
    logger.debug("Parsed %d price points from ENTSO-E", len(df))
    return df


def _parse_load_document(xml_text: str) -> pd.DataFrame:
    """
    Parse a GL_MarketDocument (actual total load) XML response.

    Returns a DataFrame indexed by UTC timestamp with a ``load_mw`` column.
    """
    ns_uri = _detect_namespace(xml_text)
    if ns_uri is None:
        logger.error("ENTSO-E load response: cannot detect XML namespace")
        return pd.DataFrame()

    ns = {"g": ns_uri}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("ENTSO-E load response: XML parse error: %s", exc)
        return pd.DataFrame()

    records: list[dict] = []

    for ts_el in root.findall(".//g:TimeSeries", ns):
        period = ts_el.find("g:Period", ns)
        if period is None:
            continue

        time_interval = period.find("g:timeInterval", ns)
        if time_interval is None:
            continue

        start_raw = _find_text(time_interval, "g:start", ns)
        if start_raw is None:
            continue
        try:
            period_start = _parse_entsoe_datetime(start_raw)
        except (ValueError, TypeError):
            continue

        resolution_raw = _find_text(period, "g:resolution", ns) or "PT60M"
        res_match = re.match(r"PT(\d+)M", resolution_raw)
        resolution_minutes = int(res_match.group(1)) if res_match else 60

        for point in period.findall("g:Point", ns):
            pos_text = _find_text(point, "g:position", ns)
            qty_text = _find_text(point, "g:quantity", ns)
            if pos_text is None or qty_text is None:
                continue
            try:
                position = int(pos_text)
                quantity = float(qty_text)
            except (ValueError, TypeError):
                continue

            ts = period_start + timedelta(minutes=resolution_minutes * (position - 1))
            records.append({"timestamp": ts, "load_mw": quantity})

    if not records:
        logger.warning("ENTSO-E load document: no data points parsed")
        return pd.DataFrame()

    df = (
        pd.DataFrame(records)
        .drop_duplicates(subset=["timestamp"])
        .set_index("timestamp")
        .sort_index()
    )
    logger.debug("Parsed %d load points from ENTSO-E", len(df))
    return df


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def fetch_day_ahead_prices(
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Fetch Day-Ahead electricity prices for the DE-LU bidding zone.

    Parameters
    ----------
    start:
        Start of the query window (inclusive).
    end:
        End of the query window (exclusive).

    Returns
    -------
    pd.DataFrame
        Indexed by UTC timestamp with column ``price_eur_mwh``.
        Returns an empty DataFrame if no API key is configured or the
        request fails.
    """
    api_key = getattr(settings, "entsoe_api_key", None)
    if not api_key:
        logger.info(
            "ENTSO-E: no API key configured — skipping Day-Ahead price fetch"
        )
        return pd.DataFrame(columns=["price_eur_mwh"])

    params = {
        "securityToken": api_key,
        "documentType": DOC_TYPE_PRICES,
        "in_Domain": DE_LU_BIDDING_ZONE,
        "out_Domain": DE_LU_BIDDING_ZONE,
        "periodStart": _format_ts(start),
        "periodEnd": _format_ts(end),
    }

    logger.info(
        "Fetching ENTSO-E Day-Ahead prices: %s → %s",
        _format_ts(start),
        _format_ts(end),
    )

    async with httpx.AsyncClient(
        headers={"Accept": "application/xml"},
        follow_redirects=True,
    ) as client:
        try:
            xml_text = await _get_with_retry(client, params)
        except Exception as exc:  # noqa: BLE001
            logger.error("ENTSO-E Day-Ahead price fetch failed: %s", exc)
            return pd.DataFrame(columns=["price_eur_mwh"])

    is_err, reason = _is_error_response(xml_text)
    if is_err:
        logger.error("ENTSO-E returned error for price request: %s", reason)
        return pd.DataFrame(columns=["price_eur_mwh"])

    df = _parse_price_document(xml_text)
    logger.info(
        "ENTSO-E Day-Ahead prices: %d rows retrieved (%.1f hours)",
        len(df),
        len(df),  # each row is one hour
    )
    return df


async def fetch_actual_load(
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Fetch actual total load for the DE-LU bidding zone.

    Parameters
    ----------
    start:
        Start of the query window (inclusive).
    end:
        End of the query window (exclusive).

    Returns
    -------
    pd.DataFrame
        Indexed by UTC timestamp with column ``load_mw``.
        Returns an empty DataFrame if no API key is configured or the
        request fails.
    """
    api_key = getattr(settings, "entsoe_api_key", None)
    if not api_key:
        logger.info(
            "ENTSO-E: no API key configured — skipping actual load fetch"
        )
        return pd.DataFrame(columns=["load_mw"])

    params = {
        "securityToken": api_key,
        "documentType": DOC_TYPE_LOAD,
        "processType": PROCESS_TYPE_REALISED,
        "outBiddingZone_Domain": DE_LU_BIDDING_ZONE,
        "periodStart": _format_ts(start),
        "periodEnd": _format_ts(end),
    }

    logger.info(
        "Fetching ENTSO-E actual load: %s → %s",
        _format_ts(start),
        _format_ts(end),
    )

    async with httpx.AsyncClient(
        headers={"Accept": "application/xml"},
        follow_redirects=True,
    ) as client:
        try:
            xml_text = await _get_with_retry(client, params)
        except Exception as exc:  # noqa: BLE001
            logger.error("ENTSO-E actual load fetch failed: %s", exc)
            return pd.DataFrame(columns=["load_mw"])

    is_err, reason = _is_error_response(xml_text)
    if is_err:
        logger.error("ENTSO-E returned error for load request: %s", reason)
        return pd.DataFrame(columns=["load_mw"])

    df = _parse_load_document(xml_text)
    logger.info("ENTSO-E actual load: %d rows retrieved", len(df))
    return df
