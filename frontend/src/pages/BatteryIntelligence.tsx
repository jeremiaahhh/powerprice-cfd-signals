import React, { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { Battery, Zap, TrendingDown, TrendingUp, AlertTriangle, CheckCircle, Info } from 'lucide-react'
import {
  getBatteryLatest, getBatteryFlows, getBatteryDataQuality, getBatteryRegimeImpact,
  BatteryLatest, BatteryFlowPoint, BatteryDataQuality, BatteryRegimeImpact
} from '../api/client'
import { format } from 'date-fns'

function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return (v * 100).toFixed(1) + '%'
}

function mw(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('de-DE', { maximumFractionDigits: 0 }) + ' MW'
}

function qualityColor(score: number): string {
  if (score >= 0.8) return 'text-green-400'
  if (score >= 0.5) return 'text-yellow-400'
  return 'text-orange-400'
}

function qualityLabel(score: number): string {
  if (score >= 0.8) return 'High'
  if (score >= 0.5) return 'Medium'
  return 'Proxy'
}

function SaturationBar({ value, label }: { value: number | null; label: string }) {
  const v = value ?? 0
  const pctVal = Math.round(v * 100)
  const color = v > 0.85 ? 'bg-red-500' : v > 0.65 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-400">
        <span>{label}</span>
        <span>{pctVal}%</span>
      </div>
      <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pctVal}%` }} />
      </div>
    </div>
  )
}

export default function BatteryIntelligence() {
  const [latest, setLatest]   = useState<BatteryLatest | null>(null)
  const [flows, setFlows]     = useState<BatteryFlowPoint[]>([])
  const [quality, setQuality] = useState<BatteryDataQuality | null>(null)
  const [impact, setImpact]   = useState<BatteryRegimeImpact | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getBatteryLatest(),
      getBatteryFlows(48),
      getBatteryDataQuality(),
      getBatteryRegimeImpact(),
    ])
      .then(([l, f, q, i]) => {
        setLatest(l)
        setFlows(f)
        setQuality(q)
        setImpact(i)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const proxy = latest?.latest_proxy
  const cap   = latest?.capacity

  // Prepare chart data
  const chartData = flows.map(f => ({
    time: format(new Date(f.timestamp), 'HH:mm dd.MM'),
    charging: Math.round(f.charging_mw),
    discharging: Math.round(f.discharging_mw),
    net: Math.round(f.net_battery_flow_mw),
  }))

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
          <AlertTriangle className="inline mr-2" size={16} />
          {error}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Battery size={24} className="text-blue-400" />
        <div>
          <h1 className="text-xl font-semibold text-white">Battery Intelligence</h1>
          <p className="text-sm text-gray-400">German grid battery storage — structural market factor</p>
        </div>
        {quality?.is_proxy && (
          <span className="ml-auto bg-yellow-900/40 border border-yellow-700 text-yellow-300 text-xs px-2 py-1 rounded flex items-center gap-1">
            <Info size={12} /> Proxy data
          </span>
        )}
      </div>

      {/* Data source warning */}
      {quality?.is_proxy && (
        <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-3 text-sm text-yellow-300 flex gap-2">
          <Info size={16} className="flex-shrink-0 mt-0.5" />
          <span>{quality.note}</span>
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <p className="text-xs text-gray-400 mb-1">Installed Power</p>
          <p className="text-2xl font-bold text-white">{cap ? Math.round(cap.power_mw / 1000) : '—'} GW</p>
          <p className="text-xs text-gray-500 mt-1">{cap?.source ?? '—'}</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <p className="text-xs text-gray-400 mb-1">Installed Capacity</p>
          <p className="text-2xl font-bold text-white">{cap ? Math.round(cap.capacity_mwh / 1000) : '—'} GWh</p>
          <p className="text-xs text-gray-500 mt-1">~{cap ? Math.round((cap.capacity_mwh / cap.power_mw) * 10) / 10 : '—'}h avg duration</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <p className="text-xs text-gray-400 mb-1">Data Quality</p>
          <p className={`text-2xl font-bold ${qualityColor(quality?.data_quality_score ?? 0)}`}>
            {qualityLabel(quality?.data_quality_score ?? 0)}
          </p>
          <p className="text-xs text-gray-500 mt-1">score: {((quality?.data_quality_score ?? 0) * 100).toFixed(0)}%</p>
        </div>
        <div className={`rounded-lg p-4 border ${impact?.hc_signal_blocked ? 'bg-red-900/20 border-red-700' : 'bg-green-900/20 border-green-700'}`}>
          <p className="text-xs text-gray-400 mb-1">HC Signal</p>
          {impact?.hc_signal_blocked ? (
            <>
              <p className="text-2xl font-bold text-red-400">Blocked</p>
              <p className="text-xs text-red-400 mt-1">Battery guard active</p>
            </>
          ) : (
            <>
              <p className="text-2xl font-bold text-green-400">Clear</p>
              <p className="text-xs text-green-400 mt-1">Battery guard passed</p>
            </>
          )}
        </div>
      </div>

      {/* Battery state + regime */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Battery state */}
        <div className="bg-gray-800 rounded-lg p-5 border border-gray-700 space-y-4">
          <h3 className="text-sm font-medium text-gray-300">Storage State</h3>
          <SaturationBar value={proxy?.battery_saturation_proxy ?? null} label="Battery Saturation (SoC proxy)" />
          <SaturationBar value={proxy?.storage_charge_pressure ?? null} label="Charge Pressure" />
          <SaturationBar value={proxy?.storage_discharge_pressure ?? null} label="Discharge Pressure" />
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="text-center">
              <TrendingDown size={16} className="text-blue-400 mx-auto mb-1" />
              <p className="text-xs text-gray-400">Charging</p>
              <p className="text-sm font-medium text-blue-300">{mw(proxy?.battery_charging_mw)}</p>
            </div>
            <div className="text-center">
              <TrendingUp size={16} className="text-orange-400 mx-auto mb-1" />
              <p className="text-xs text-gray-400">Discharging</p>
              <p className="text-sm font-medium text-orange-300">{mw(proxy?.battery_discharging_mw)}</p>
            </div>
          </div>
          <div className="text-center pt-1 border-t border-gray-700">
            <p className="text-xs text-gray-400">Net Battery Flow</p>
            <p className={`text-lg font-bold ${(proxy?.net_battery_flow_mw ?? 0) >= 0 ? 'text-orange-300' : 'text-blue-300'}`}>
              {proxy?.net_battery_flow_mw != null
                ? `${proxy.net_battery_flow_mw >= 0 ? '+' : ''}${Math.round(proxy.net_battery_flow_mw)} MW`
                : '—'}
            </p>
            <p className="text-xs text-gray-500">{(proxy?.net_battery_flow_mw ?? 0) >= 0 ? 'net generation' : 'net charging'}</p>
          </div>
        </div>

        {/* Regime impact */}
        <div className="bg-gray-800 rounded-lg p-5 border border-gray-700 space-y-3">
          <h3 className="text-sm font-medium text-gray-300">Regime Impact</h3>
          {impact && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Current Regime</span>
                <span className="text-sm font-medium text-blue-300">{impact.regime.regime.replace(/_/g, ' ')}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Enter threshold</span>
                <span className="text-sm font-mono text-white">{impact.regime.signal_thresholds.net_edge_enter} EUR/MWh</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">HC threshold</span>
                <span className="text-sm font-mono text-white">{impact.regime.signal_thresholds.net_edge_hc} EUR/MWh</span>
              </div>
              <p className="text-xs text-gray-400 border-t border-gray-700 pt-3">{impact.regime.description}</p>
              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-400">Expected absorption</span>
                  <span className="text-gray-300">{mw(impact.battery_state.expected_battery_absorption)}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-400">Expected release</span>
                  <span className="text-gray-300">{mw(impact.battery_state.expected_battery_release)}</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Charge/discharge chart */}
      <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
        <h3 className="text-sm font-medium text-gray-300 mb-4">Battery Flows (48h proxy)</h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="colorCharge" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorDischarge" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ca3af' }} interval={5} />
              <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={v => `${Math.round(v / 1000)}k`} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(v: number, name: string) => [`${Math.round(v).toLocaleString()} MW`, name]}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
              <Area type="monotone" dataKey="charging" name="Charging (↓)" stroke="#3b82f6" fill="url(#colorCharge)" strokeWidth={1.5} />
              <Area type="monotone" dataKey="discharging" name="Discharging (↑)" stroke="#f97316" fill="url(#colorDischarge)" strokeWidth={1.5} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-gray-500 text-sm text-center py-8">No flow data available</p>
        )}
      </div>

      {/* PV surplus + arbitrage */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={16} className="text-yellow-400" />
            <h3 className="text-sm font-medium text-gray-300">PV Surplus after Load</h3>
          </div>
          <p className="text-2xl font-bold text-yellow-300">{mw(proxy?.pv_surplus_after_load)}</p>
          <p className="text-xs text-gray-500 mt-1">Excess renewable generation above load</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={16} className="text-green-400" />
            <h3 className="text-sm font-medium text-gray-300">Evening Arbitrage Spread</h3>
          </div>
          <p className="text-2xl font-bold text-green-300">
            {proxy?.evening_arbitrage_spread != null
              ? `${proxy.evening_arbitrage_spread.toFixed(1)} EUR/MWh`
              : '—'}
          </p>
          <p className="text-xs text-gray-500 mt-1">6h high–low spread (evening window)</p>
        </div>
      </div>

      {/* Footer note */}
      <div className="text-xs text-gray-600 space-y-1 border-t border-gray-800 pt-4">
        <p>
          <strong className="text-gray-500">Why batteries matter:</strong> Batteries charge during negative price events (PV surplus / wind excess),
          absorbing supply that would otherwise extend negative prices. When batteries approach capacity limits,
          the price rebound may be weaker or delayed. Batteries also discharge during evening demand spikes,
          competing with conventional rebound patterns.
        </p>
        <p>
          Proxy data quality score: {((quality?.data_quality_score ?? 0) * 100).toFixed(0)}% ·
          Source: {quality?.data_source ?? '—'} ·
          Set <code className="text-gray-400">ENTSOE_API_KEY</code> in .env for real pumped-storage data.
        </p>
      </div>
    </div>
  )
}
