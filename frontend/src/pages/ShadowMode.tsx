import { useEffect, useState } from 'react'
import { getRollingPerformance, getDaemonStatus, RollingPerformance, DaemonStatus } from '../api/client'

const BASE_URL = '/api'

interface LiveSignal {
  id?: number
  timestamp: string
  action: string
  current_price: number
  p_rebound: number
  net_edge: number
  tail_risk_score: number
}

function PfBadge({ pf }: { pf: number | null }) {
  if (pf == null) return <span className="text-gray-500 font-mono">—</span>
  const cls = pf >= 1.3 ? 'text-green-400' : pf >= 1.0 ? 'text-yellow-400' : 'text-red-400'
  return <span className={`text-2xl font-mono font-bold ${cls}`}>{pf.toFixed(2)}</span>
}

function WinRateBadge({ rate }: { rate: number | null }) {
  if (rate == null) return <span className="text-gray-500 font-mono">—</span>
  const cls = rate >= 60 ? 'text-green-400' : rate >= 50 ? 'text-yellow-400' : 'text-red-400'
  return <span className={`text-2xl font-mono font-bold ${cls}`}>{rate.toFixed(1)}%</span>
}

export default function ShadowMode() {
  const [perf, setPerf] = useState<RollingPerformance | null>(null)
  const [daemonStatus, setDaemonStatus] = useState<DaemonStatus | null>(null)
  const [liveSignals, setLiveSignals] = useState<LiveSignal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState('')

  const fetchAll = async () => {
    try {
      const [p, d] = await Promise.all([
        getRollingPerformance(30),
        getDaemonStatus(),
      ])
      setPerf(p)
      setDaemonStatus(d)

      // Live signals — best effort, may not exist
      try {
        const res = await fetch(`${BASE_URL}/shadow/live-signals`)
        if (res.ok) {
          const data = await res.json()
          setLiveSignals(Array.isArray(data) ? data : data.signals ?? [])
        }
      } catch {
        // endpoint may not be implemented yet
      }

      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to load shadow mode data')
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
        Loading shadow mode data...
      </div>
    </div>
  )

  if (error) return (
    <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
      Error: {error}
    </div>
  )

  const signalMode = daemonStatus?.signal_mode ?? 'NORMAL'
  const isWatchOnly = signalMode === 'WATCH_ONLY'

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white font-mono">SHADOW MODE</h1>
        <span className="text-xs text-gray-500">Updated {lastUpdate} · auto-refreshes 30s</span>
      </div>

      {/* Watch-only warning */}
      {isWatchOnly && (
        <div className="bg-orange-900/40 border border-orange-700 rounded-lg p-3">
          <div className="flex items-center gap-2">
            <span className="text-orange-300 font-mono font-bold text-sm">WATCH_ONLY MODE ACTIVE</span>
          </div>
          <p className="text-orange-300/80 text-xs mt-1">
            The signal mode has been downgraded to WATCH_ONLY because rolling profit factor fell below the floor threshold.
            Signals are being generated and evaluated but entry conditions are suppressed.
            Mode will recover to NORMAL when PF exceeds the recovery threshold.
          </p>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-500 mb-1">Rolling PF (30d)</div>
          <PfBadge pf={perf?.rolling_pf ?? null} />
          <div className="text-xs text-gray-600 mt-1">
            {perf?.rolling_pf == null ? '' : perf.rolling_pf >= 1.3 ? 'Good' : perf.rolling_pf >= 1.0 ? 'Marginal' : 'Below floor'}
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-500 mb-1">Rolling Win Rate (30d)</div>
          <WinRateBadge rate={perf?.rolling_win_rate ?? null} />
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-500 mb-1">Sample Size</div>
          <span className="text-2xl font-mono font-bold text-white">{perf?.sample_size ?? '—'}</span>
          <div className="text-xs text-gray-500 mt-1">outcomes</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-500 mb-1">Signal Mode</div>
          <span className={`text-sm font-mono font-bold ${isWatchOnly ? 'text-orange-400' : 'text-green-400'}`}>
            {signalMode}
          </span>
        </div>
      </div>

      {/* Live Signals Table */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-sm font-mono text-gray-300">LIVE SIGNALS</h2>
          <span className="text-xs text-gray-500">{liveSignals.length} signals</span>
        </div>
        {liveSignals.length === 0 ? (
          <div className="px-4 py-6 text-center text-gray-500 text-sm">No live signals available.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-700 text-gray-500 text-left">
                  <th className="px-4 py-2">Time</th>
                  <th className="px-4 py-2">Action</th>
                  <th className="px-4 py-2">Price</th>
                  <th className="px-4 py-2">p_rebound</th>
                  <th className="px-4 py-2">Net Edge</th>
                  <th className="px-4 py-2">Tail Risk</th>
                </tr>
              </thead>
              <tbody>
                {liveSignals.map((sig, i) => (
                  <tr key={sig.id ?? i} className="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors">
                    <td className="px-4 py-2 font-mono text-gray-300 whitespace-nowrap">
                      {new Date(sig.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`font-mono text-xs font-bold ${
                        sig.action.includes('ENTER') || sig.action.includes('HIGH') ? 'text-green-400' :
                        sig.action.includes('WATCH') ? 'text-yellow-400' :
                        sig.action.includes('BLOCKED') ? 'text-red-400' : 'text-gray-400'
                      }`}>{sig.action}</span>
                    </td>
                    <td className="px-4 py-2 font-mono text-white">{sig.current_price?.toFixed(2) ?? '—'}</td>
                    <td className="px-4 py-2 font-mono">
                      <span className={sig.p_rebound >= 0.7 ? 'text-green-400' : sig.p_rebound >= 0.5 ? 'text-yellow-400' : 'text-red-400'}>
                        {sig.p_rebound?.toFixed(3) ?? '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono">
                      <span className={sig.net_edge >= 35 ? 'text-green-400' : sig.net_edge >= 10 ? 'text-yellow-400' : 'text-red-400'}>
                        {sig.net_edge?.toFixed(1) ?? '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono">
                      <span className={sig.tail_risk_score <= 0.3 ? 'text-green-400' : sig.tail_risk_score <= 0.65 ? 'text-yellow-400' : 'text-red-400'}>
                        {sig.tail_risk_score?.toFixed(3) ?? '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {perf?.generated_at && (
        <div className="text-xs text-gray-600">Performance data generated at: {new Date(perf.generated_at).toLocaleString()}</div>
      )}
    </div>
  )
}
