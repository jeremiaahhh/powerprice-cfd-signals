import { useEffect, useState } from 'react'
import { getRiskTail, getRiskGap, getRiskVolatility, TailRiskAssessment, GapAssessment, VolatilityAssessment } from '../api/client'

function ScoreBar({ label, value, max = 1 }: { label: string; value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100)
  const color = value < 0.3 ? 'bg-green-500' : value < 0.65 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-400">{label}</span>
        <span className={value < 0.3 ? 'text-green-400' : value < 0.65 ? 'text-yellow-400' : 'text-red-400'}>
          {value.toFixed(3)}
        </span>
      </div>
      <div className="w-full bg-gray-700 rounded-full h-2">
        <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function VolBadge({ regime }: { regime: string }) {
  const cls = regime === 'NORMAL' ? 'bg-green-900 text-green-300' :
               regime === 'ELEVATED' ? 'bg-yellow-900 text-yellow-300' : 'bg-red-900 text-red-300'
  return <span className={`px-2 py-1 rounded text-xs font-mono font-bold ${cls}`}>{regime}</span>
}

export default function TailRiskMonitor() {
  const [tail, setTail] = useState<TailRiskAssessment | null>(null)
  const [gap, setGap] = useState<GapAssessment | null>(null)
  const [vol, setVol] = useState<VolatilityAssessment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string>('')

  const fetchAll = async () => {
    try {
      const [t, g, v] = await Promise.all([getRiskTail(), getRiskGap(), getRiskVolatility()])
      setTail(t)
      setGap(g)
      setVol(v)
      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to load risk data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 30_000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3" />
        Loading tail risk data...
      </div>
    </div>
  )

  if (error) return (
    <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
      Error: {error}
    </div>
  )

  const isAnyBlocked = tail?.is_blocked || vol?.is_blocked

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white font-mono">TAIL RISK MONITOR</h1>
        <span className="text-xs text-gray-500">Updated {lastUpdate} · auto-refreshes 30s</span>
      </div>

      {isAnyBlocked && (
        <div className="bg-red-900/50 border border-red-600 rounded-lg p-3 flex items-center gap-2">
          <span className="text-red-300 text-sm font-mono font-bold">
            ⚠ ENTRY BLOCKED — {tail?.block_reason || 'EXTREME_VOLATILITY'}
          </span>
          <span className="text-red-400 text-xs">{tail?.block_detail || vol?.detail}</span>
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          {
            label: 'Tail Risk Score', value: tail?.tail_risk_score ?? 0,
            badge: (tail?.tail_risk_score ?? 0) < 0.3 ? 'LOW' : (tail?.tail_risk_score ?? 0) < 0.65 ? 'MEDIUM' : 'HIGH',
            color: (tail?.tail_risk_score ?? 0) < 0.3 ? 'text-green-400' : (tail?.tail_risk_score ?? 0) < 0.65 ? 'text-yellow-400' : 'text-red-400',
          },
          {
            label: 'Gap Risk Score', value: tail?.gap_risk_score ?? 0,
            badge: (tail?.gap_risk_score ?? 0) < 0.3 ? 'LOW' : (tail?.gap_risk_score ?? 0) < 0.65 ? 'MED' : 'HIGH',
            color: (tail?.gap_risk_score ?? 0) < 0.3 ? 'text-green-400' : 'text-yellow-400',
          },
          {
            label: 'Neg. Streak', value: tail?.negative_price_streak ?? 0,
            badge: `${tail?.negative_price_streak ?? 0}h`,
            color: (tail?.negative_price_streak ?? 0) <= 3 ? 'text-green-400' : 'text-red-400',
            isRaw: true,
          },
          {
            label: 'Vol. Regime', value: 0,
            badge: vol?.regime ?? 'N/A',
            color: vol?.regime === 'NORMAL' ? 'text-green-400' : vol?.regime === 'ELEVATED' ? 'text-yellow-400' : 'text-red-400',
            isRaw: true,
          },
        ].map((kpi) => (
          <div key={kpi.label} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-500 mb-1">{kpi.label}</div>
            {kpi.isRaw ? (
              <div className={`text-2xl font-mono font-bold ${kpi.color}`}>{kpi.badge}</div>
            ) : (
              <>
                <div className={`text-2xl font-mono font-bold ${kpi.color}`}>
                  {(kpi.value as number).toFixed(3)}
                </div>
                <div className={`text-xs font-mono mt-1 ${kpi.color}`}>{kpi.badge}</div>
              </>
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Composite breakdown */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-sm font-mono text-gray-300 mb-4">COMPOSITE RISK BREAKDOWN</h2>
          {tail && (
            <>
              <ScoreBar label="Gap Risk" value={tail.gap_risk_score} />
              <ScoreBar label="Oversupply Stress" value={tail.oversupply_stress_index} />
              <ScoreBar label="Rebound Failure Prob." value={tail.rebound_failure_probability} />
              <ScoreBar label="Composite (tail_risk_score)" value={tail.tail_risk_score} />
              <div className="mt-3 pt-3 border-t border-gray-700 text-xs text-gray-500">
                Max 1h gap: <span className="text-white">{tail.max_price_gap_1h.toFixed(1)} EUR/MWh</span>
                &nbsp;·&nbsp; 24h vol: <span className="text-white">{tail.volatility_24h.toFixed(1)} EUR/MWh</span>
                &nbsp;·&nbsp; Current: <span className="text-white">{tail.current_price.toFixed(1)} EUR/MWh</span>
              </div>
            </>
          )}
        </div>

        {/* Volatility + Gap */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-sm font-mono text-gray-300 mb-4">VOLATILITY & GAP DETAIL</h2>
          {vol && (
            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between">
                <span className="text-gray-400">Regime</span>
                <VolBadge regime={vol.regime} />
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">6h volatility</span>
                <span className="text-white font-mono">{vol.vol_6h.toFixed(1)} EUR/MWh</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">24h volatility</span>
                <span className="text-white font-mono">{vol.vol_24h.toFixed(1)} EUR/MWh</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Spike ratio</span>
                <span className={`font-mono ${vol.vol_spike_ratio > 2.5 ? 'text-red-400' : 'text-white'}`}>
                  {vol.vol_spike_ratio.toFixed(2)}x
                </span>
              </div>
            </div>
          )}
          {gap && (
            <div className="space-y-2 text-sm border-t border-gray-700 pt-3">
              <div className="flex justify-between">
                <span className="text-gray-400">Max 1h gap (12h window)</span>
                <span className={`font-mono ${gap.has_extreme_gap ? 'text-red-400' : 'text-white'}`}>
                  {gap.max_gap_1h.toFixed(1)} EUR/MWh
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Extreme gaps detected</span>
                <span className={`font-mono ${gap.has_extreme_gap ? 'text-red-400' : 'text-green-400'}`}>
                  {gap.has_extreme_gap ? `YES (${gap.gap_timestamps.length})` : 'None'}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Production rules */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-sm font-mono text-gray-300 mb-3">NEW PRODUCTION RULES (2026-05-20)</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs font-mono">
          {[
            'p_rebound ≥ 0.70',
            'streak ≤ 3h',
            'price > −150 EUR/MWh',
            'tail_risk_score ≤ 0.65',
            'gap_risk_score ≤ 0.80',
            'net_edge ≥ 35 EUR/MWh',
            'vol_regime ≠ EXTREME',
            'data_quality OK',
            'no_extreme_gap = true',
          ].map(rule => (
            <div key={rule} className="flex items-center gap-1 text-gray-400">
              <span className="text-green-500">✓</span> {rule}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
