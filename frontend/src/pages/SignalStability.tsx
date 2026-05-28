import { useEffect, useState } from 'react'
import { getOOSPerformance, getRegimeDrift, OOSPerformance, OOSPerformanceRun } from '../api/client'

function MetricBadge({ value, good, bad }: { value: number | null; good: number; bad: number }) {
  if (value === null) return <span className="text-gray-500 font-mono">N/A</span>
  const color = value >= good ? 'text-green-400' : value <= bad ? 'text-red-400' : 'text-yellow-400'
  return <span className={`font-mono ${color}`}>{value.toFixed(2)}</span>
}

export default function SignalStability() {
  const [perf, setPerf] = useState<OOSPerformance | null>(null)
  const [drift, setDrift] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getOOSPerformance(), getRegimeDrift(30)])
      .then(([p, d]) => { setPerf(p); setDrift(d) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto" />
    </div>
  )
  if (error) return <div className="text-red-400 p-4">Error: {error}</div>

  const summary = perf?.summary
  const mlRuns = (perf?.runs ?? []).filter((r: OOSPerformanceRun) => r.strategy === 'ml_rebound')

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white font-mono">SIGNAL STABILITY — OOS PERFORMANCE</h1>
      </div>

      <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-3 text-xs text-blue-300 font-mono">
        ℹ All ML backtests use train_before_start_date — no look-ahead bias. Walk-forward retrains every 90 days.
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'ML Runs', value: summary?.ml_runs_count ?? 0, fmt: (v: number) => v.toString(), color: (_v: number) => 'text-white' },
          { label: 'Avg Sharpe', value: summary?.avg_sharpe ?? null, fmt: (v: number) => v.toFixed(2), color: (v: number) => v > 0.5 ? 'text-green-400' : 'text-yellow-400' },
          { label: 'Avg Win Rate', value: summary?.avg_win_rate ?? null, fmt: (v: number) => `${v.toFixed(1)}%`, color: (v: number) => v > 55 ? 'text-green-400' : 'text-yellow-400' },
          { label: 'Avg Profit Factor', value: summary?.avg_profit_factor ?? null, fmt: (v: number) => v.toFixed(2), color: (v: number) => v > 1.1 ? 'text-green-400' : 'text-red-400' },
        ].map(kpi => (
          <div key={kpi.label} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-500 mb-1">{kpi.label}</div>
            <div className={`text-2xl font-mono font-bold ${kpi.value === null ? 'text-gray-500' : kpi.color(kpi.value as number)}`}>
              {kpi.value === null ? 'N/A' : kpi.fmt(kpi.value as number)}
            </div>
          </div>
        ))}
      </div>

      {/* Run table */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-sm font-mono text-gray-300 mb-3">OOS BACKTEST RUNS</h2>
        {mlRuns.length === 0 ? (
          <p className="text-gray-500 text-sm">No ML backtest runs yet. Run POST /backtest/run to generate.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="text-left py-2 pr-4">Period</th>
                  <th className="text-right py-2 pr-4">Trades</th>
                  <th className="text-right py-2 pr-4">Win%</th>
                  <th className="text-right py-2 pr-4">Sharpe</th>
                  <th className="text-right py-2 pr-4">MaxDD%</th>
                  <th className="text-right py-2 pr-4">Return%</th>
                  <th className="text-right py-2 pr-4">PF</th>
                  <th className="text-right py-2">Worst</th>
                </tr>
              </thead>
              <tbody>
                {mlRuns.map((r: OOSPerformanceRun) => (
                  <tr key={r.run_id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                    <td className="py-2 pr-4 text-gray-300">
                      {r.start_date?.slice(0,7)} → {r.end_date?.slice(0,7)}
                    </td>
                    <td className="text-right py-2 pr-4 text-white">{r.total_trades ?? '—'}</td>
                    <td className="text-right py-2 pr-4">
                      <MetricBadge value={r.win_rate_pct} good={60} bad={40} />
                    </td>
                    <td className="text-right py-2 pr-4">
                      <MetricBadge value={r.sharpe_ratio} good={0.5} bad={0} />
                    </td>
                    <td className="text-right py-2 pr-4">
                      {r.max_drawdown_pct !== null ? (
                        <span className={r.max_drawdown_pct > 200 ? 'text-red-400' : 'text-yellow-400'}>
                          {r.max_drawdown_pct?.toFixed(1)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="text-right py-2 pr-4">
                      {r.total_return_pct !== null ? (
                        <span className={r.total_return_pct > 0 ? 'text-green-400' : 'text-red-400'}>
                          {r.total_return_pct?.toFixed(1)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="text-right py-2 pr-4">
                      <MetricBadge value={r.profit_factor} good={1.2} bad={1.0} />
                    </td>
                    <td className="text-right py-2">
                      {r.worst_trade_eur_mwh !== null ? (
                        <span className="text-red-400">{r.worst_trade_eur_mwh?.toFixed(1)}</span>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Regime drift */}
      {drift && drift.status === 'ok' && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-sm font-mono text-gray-300 mb-3">
            REGIME DRIFT ({drift.days_analyzed}d, {drift.total_snapshots} snapshots)
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="text-left py-2 pr-4">Regime</th>
                  <th className="text-right py-2 pr-4">Count</th>
                  <th className="text-right py-2 pr-4">%</th>
                  <th className="text-right py-2 pr-4">First half%</th>
                  <th className="text-right py-2 pr-4">Second half%</th>
                  <th className="text-right py-2">Drift (pp)</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(drift.regime_distribution ?? {}).map(([regime, info]: [string, any]) => {
                  const d = drift.drift_analysis?.[regime]
                  return (
                    <tr key={regime} className="border-b border-gray-700/50">
                      <td className="py-2 pr-4 text-gray-300">{regime}</td>
                      <td className="text-right py-2 pr-4 text-white">{info.count}</td>
                      <td className="text-right py-2 pr-4 text-gray-400">{info.pct}%</td>
                      <td className="text-right py-2 pr-4 text-gray-400">{d?.first_half_pct ?? '—'}%</td>
                      <td className="text-right py-2 pr-4 text-gray-400">{d?.second_half_pct ?? '—'}%</td>
                      <td className={`text-right py-2 ${!d ? '' : Math.abs(d.drift_pp) > 10 ? 'text-yellow-400' : 'text-gray-400'}`}>
                        {d ? `${d.drift_pp > 0 ? '+' : ''}${d.drift_pp}pp` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
