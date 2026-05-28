"""
Battery storage behavior proxy — derived from price and generation data.

Used when real-time battery flow data is unavailable (no ENTSO-E key).

Physical rationale:
  - Batteries charge when price < 10 EUR/MWh (merit order incentive)
  - Batteries discharge when price > 60 EUR/MWh or during evening demand spikes
  - PV surplus (midday) creates charge pressure proportional to surplus MW
  - State of Charge estimated by integrating net flow over rolling 24-h window

Limitations (documented transparently):
  - Does not capture individual operator decisions or ancillary-service obligations
  - Misses grid topology constraints (local congestion)
  - SoC estimate resets every 24 h; true SoC depends on multi-day history
  - is_proxy=True in all output rows; data_quality_score=0.35
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional

_DEFAULT_POWER_MW = 14_000.0
_DEFAULT_CAPACITY_MWH = 28_000.0
_CHARGE_PRICE_THR = 10.0    # EUR/MWh: charge trigger
_DISCHARGE_PRICE_THR = 60.0  # EUR/MWh: discharge trigger


def compute_storage_proxy(
    df: pd.DataFrame,
    installed_power_mw: float = _DEFAULT_POWER_MW,
    installed_capacity_mwh: float = _DEFAULT_CAPACITY_MWH,
) -> pd.DataFrame:
    """
    Derive hourly battery flow proxy from price + generation data.

    Parameters
    ----------
    df : DataFrame with at least: timestamp, price_eur_mwh.
         Optional: solar_mw, wind_onshore_mw, wind_offshore_mw, load_mw
    installed_power_mw : Total installed battery power in Germany (MW)
    installed_capacity_mwh : Total installed battery energy capacity (MWh)

    Returns
    -------
    DataFrame with columns:
        timestamp, charging_mw, discharging_mw, net_battery_flow_mw,
        pv_surplus_index, storage_charge_pressure, storage_discharge_pressure,
        midday_compression_index, evening_arbitrage_index,
        battery_saturation_proxy, source, is_proxy, data_quality_score
    """
    df = df.copy().sort_values("timestamp").reset_index(drop=True)

    def _col(name: str, fill: float) -> pd.Series:
        return df.get(name, pd.Series(fill, index=df.index)).fillna(fill)

    price  = _col("price_eur_mwh", 0.0)
    solar  = _col("solar_mw", 0.0)
    won    = _col("wind_onshore_mw", 0.0)
    woff   = _col("wind_offshore_mw", 0.0)
    load   = _col("load_mw", 55_000.0)
    ts     = pd.to_datetime(df["timestamp"])
    hour   = ts.dt.hour.astype(float)

    # --- PV surplus index --------------------------------------------------
    total_gen   = solar + won + woff
    surplus_mw  = (total_gen - load).clip(lower=0)
    pv_surplus  = (surplus_mw / max(installed_power_mw, 1.0)).clip(0, 1.0)

    # --- Charge pressure ---------------------------------------------------
    is_midday         = ((hour >= 9) & (hour <= 16)).astype(float)
    price_below       = (_CHARGE_PRICE_THR - price.clip(upper=_CHARGE_PRICE_THR)) / (_CHARGE_PRICE_THR + 50)
    charge_pressure   = (0.5 * price_below.clip(0, 1) + 0.3 * pv_surplus + 0.2 * is_midday).clip(0, 1.0)

    # --- Discharge pressure ------------------------------------------------
    is_evening        = ((hour >= 17) & (hour <= 21)).astype(float)
    price_above       = ((price - _DISCHARGE_PRICE_THR).clip(lower=0) / 100.0).clip(0, 1)
    load_high         = ((load - 55_000) / 20_000).clip(0, 1)
    discharge_pressure = (0.4 * price_above + 0.4 * is_evening + 0.2 * load_high).clip(0, 1.0)

    # --- MW estimates (can't charge and discharge simultaneously) ----------
    charging_mw    = (charge_pressure * installed_power_mw * 0.7).clip(0, installed_power_mw)
    discharging_mw = (discharge_pressure * installed_power_mw * 0.7).clip(0, installed_power_mw)
    net_flow       = discharging_mw - charging_mw  # positive = net generation

    # --- State of Charge proxy (rolling 24-h integral) --------------------
    net_charge     = -net_flow                       # positive = SoC increasing
    soc_delta      = net_charge.rolling(24, min_periods=1).sum()
    soc_norm       = ((soc_delta + installed_capacity_mwh * 0.5) / installed_capacity_mwh).clip(0, 1.0)

    # --- Midday compression index -----------------------------------------
    roll_mean_24   = price.rolling(24, min_periods=12).mean()
    midday_rel     = (price / roll_mean_24.replace(0, np.nan)).fillna(1.0)
    midday_compr   = ((1.0 - midday_rel.clip(0, 2) / 2.0) * is_midday).clip(0, 1.0)

    # --- Evening arbitrage index ------------------------------------------
    roll_min_6     = price.rolling(6, min_periods=1).min()
    roll_max_6     = price.rolling(6, min_periods=1).max()
    eve_arb        = ((roll_max_6 - roll_min_6) / 200.0).clip(0, 1.0)

    return pd.DataFrame({
        "timestamp":                 df["timestamp"].values,
        "charging_mw":               charging_mw.round(1),
        "discharging_mw":            discharging_mw.round(1),
        "net_battery_flow_mw":       net_flow.round(1),
        "pv_surplus_index":          pv_surplus.round(4),
        "storage_charge_pressure":   charge_pressure.round(4),
        "storage_discharge_pressure":discharge_pressure.round(4),
        "midday_compression_index":  midday_compr.round(4),
        "evening_arbitrage_index":   eve_arb.round(4),
        "battery_saturation_proxy":  soc_norm.round(4),
        "source":                    "proxy",
        "is_proxy":                  True,
        "data_quality_score":        0.35,
    })
