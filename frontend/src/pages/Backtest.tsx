import React, { useState, useCallback } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell, Legend
} from 'recharts'
import { Play, AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react'
import { format, subDays } from 'date-fns'
import clsx from 'clsx'
import { runBacktest, BacktestResult, BacktestMetrics } from '../api/client'

// Demo data generator
function generateMockBacktest(start: string, end: string): BacktestResult {
  const naiveTrades = 45
  const mlTrades = 38

  const naiveEquity = Array.from({ length: 30 }, (_, i) => ({
    timestamp: format(subDays(new Date(end), 30 - i), 'MM-dd'),
    equity: 1000 + (i * 12) + (Math.random() - 0.4) * 60
  }))

  const mlEquity = Array.from({ length: 30 }, (_, i) => ({
    timestamp: format(subDays(new Date(end), 30 - i), 'MM-dd'),
    equity: 1000 + (i * 18) + (Math.random() - 0.35) * 40
  }))

  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
  const naiveMonthly = months.map(m => ({ month: m, return_pct: (Math.random() - 0.3) * 20 }))
  const mlMonthly = months.map(m => ({ month: m, return_pct: (Math.random() - 0.25) * 20 }))

  return {
    start_date: start,
    end_date: end,
    naive: {
      total_trades: naiveTrades,
      win_rate: 0.51,
      profit_factor: 1.12,
      total_pnl: 540,
      max_drawdown: -0.18,
      sharpe_ratio: 0.85,
      avg_trade_pnl: 12.0,
      equity_curve: naiveEquity,
      monthly_returns: naiveMonthly,
      trades: []
    },
    ml: {
      total_trades: mlTrades,
      win_rate: 0.68,
      profit_factor: 2.14,
      total_pnl: 1284,
      max_drawdown: -0.09,
      sharpe_ratio: 1.92,
      avg_trade_pnl: 33.8,
      equity_curve: mlEquity,
      monthly_returns: mlMonthly,
      trades: []
    }
  }
}

function MetricRow({ label, naive, ml, format: fmt = (v: number) => v.toFixed(2), higherIsBetter = true }: {
  label: string
  naive: number
  ml: number
  format?: (v: number) => string
  higherIsBetter?: boolean
}) {
  const mlBetter = higherIsBetter ? ml > naive : ml < naive

  return (
    <tr className="border-b border-[#1e2d4a]/50 hover:bg-[#0f1629] transition-colors">
      <td className="px-3 py-2.5 text-[11px] text-[#8892b0] font-mono">{label}</td>
      <td className="px-3 py-2.5 text-[11px] text-[#e8eaf0] font-mono tabular-nums text-right">{fmt(naive)}</td>
      <td className="px-3 py-2.5 text-right">
        <span className={clsx(
          'px-2 py-0.5 rounded text-[11px] font-mono tabular-nums font-semibold',
          mlBetter ? 'text-[#00d4aa] bg-[#00d4aa]/10' : 'text-[#e8eaf0]'
        )}>
          {fmt(ml)}
          {mlBetter && <span className="ml-1 text-[9px]">▲</span>}
        </span>
      </td>
    </tr>
  )
}

const MONTH_COLORS = (v: number) =>
  v > 10 ? '#00d4aa' : v > 3 ? '#2196f3' : v > 0 ? '#4a9f7a' :
  v > -3 ? '#ffa726' : v > -10 ? '#ff7043' : '#ff4757'

export default function Backtest() {
  const today = new Date()
  const [startDate, setStartDate] = useState(format(subDays(today, 90), 'yyyy-MM-dd'))
  const [endDate, setEndDate] = useState(format(today, 'yyyy-MM-dd'))
  const [strategy, setStrategy] = useState<'both' | 'naive' | 'ml'>('both')
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeView, setActiveView] = useState<'equity' | 'monthly'>('equity')

  const handleRun = useCallback(async () => {
    if (!startDate || !endDate) return
    setLoading(true)
    setError(null)
    try {
      const data = await runBacktest(startDate, endDate, strategy)
      setResult(data)
    } catch {
      setError('API unavailable — showing demo results')
      setResult(generateMockBacktest(startDate, endDate))
    } finally {
      setLoading(false)
    }
  }, [startDate, endDate, strategy])

  // Merged equity curve data
  const equityData = result ? result.ml.equity_curve.map((ml, i) => ({
    time: ml.timestamp,
    ml: parseFloat(ml.equity.toFixed(2)),
    naive: parseFloat((result.naive.equity_curve[i]?.equity ?? 1000).toFixed(2))
  })) : []

  const naiveMonthly = result?.naive.monthly_returns ?? []
  const mlMonthly = result?.ml.monthly_returns ?? []

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold text-[#e8eaf0] font-mono">Backtest</h1>
        <p className="text-xs text-[#4a5568] font-mono mt-0.5">
          Compare Naive vs ML strategy performance over historical period
        </p>
      </div>

      {/* Controls */}
      <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1">
            <label className="text-[9px] text-[#4a5568] font-mono uppercase tracking-wider">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="bg-[#0a0e1a] border border-[#1e2d4a] rounded px-3 py-1.5 text-[11px] font-mono text-[#e8eaf0] focus:outline-none focus:border-[#2196f3] transition-colors"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[9px] text-[#4a5568] font-mono uppercase tracking-wider">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="bg-[#0a0e1a] border border-[#1e2d4a] rounded px-3 py-1.5 text-[11px] font-mono text-[#e8eaf0] focus:outline-none focus:border-[#2196f3] transition-colors"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[9px] text-[#4a5568] font-mono uppercase tracking-wider">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as any)}
              className="bg-[#0a0e1a] border border-[#1e2d4a] rounded px-3 py-1.5 text-[11px] font-mono text-[#e8eaf0] focus:outline-none focus:border-[#2196f3] transition-colors"
            >
              <option value="both">Naive vs ML (both)</option>
              <option value="naive">Naive only</option>
              <option value="ml">ML only</option>
            </select>
          </div>
          <button
            onClick={handleRun}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-1.5 bg-[#2196f3]/10 border border-[#2196f3]/40 rounded text-[11px] font-mono text-[#2196f3] hover:bg-[#2196f3]/20 transition-all disabled:opacity-50 font-semibold"
          >
            <Play size={11} className={clsx(loading && 'animate-spin')} />
            {loading ? 'Running…' : 'Run Backtest'}
          </button>
        </div>
        {error && (
          <div className="flex items-center gap-2 mt-3 text-[10px] text-[#ffa726] font-mono">
            <AlertTriangle size={11} />
            {error}
          </div>
        )}
      </div>

      {result && (
        <>
          {/* Metrics comparison */}
          <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-[#1e2d4a] bg-[#0f1629] flex items-center justify-between">
              <h2 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider">Strategy Comparison</h2>
              <div className="flex items-center gap-4 text-[10px] font-mono">
                <span className="flex items-center gap-1.5 text-[#8892b0]">
                  <span className="w-2.5 h-2.5 rounded bg-[#8892b0]" /> Naive
                </span>
                <span className="flex items-center gap-1.5 text-[#00d4aa]">
                  <span className="w-2.5 h-2.5 rounded bg-[#00d4aa]" /> ML
                </span>
              </div>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#1e2d4a]">
                  <th className="px-3 py-2 text-left text-[9px] text-[#4a5568] uppercase font-medium font-mono">Metric</th>
                  <th className="px-3 py-2 text-right text-[9px] text-[#4a5568] uppercase font-medium font-mono">Naive</th>
                  <th className="px-3 py-2 text-right text-[9px] text-[#4a5568] uppercase font-medium font-mono">ML</th>
                </tr>
              </thead>
              <tbody>
                <MetricRow label="Total Trades" naive={result.naive.total_trades} ml={result.ml.total_trades} format={v => v.toString()} higherIsBetter={false} />
                <MetricRow label="Win Rate" naive={result.naive.win_rate} ml={result.ml.win_rate} format={v => `${(v * 100).toFixed(1)}%`} />
                <MetricRow label="Profit Factor" naive={result.naive.profit_factor} ml={result.ml.profit_factor} />
                <MetricRow label="Total PnL" naive={result.naive.total_pnl} ml={result.ml.total_pnl} format={v => `€${v.toFixed(0)}`} />
                <MetricRow label="Max Drawdown" naive={result.naive.max_drawdown} ml={result.ml.max_drawdown} format={v => `${(v * 100).toFixed(1)}%`} higherIsBetter={false} />
                <MetricRow label="Sharpe Ratio" naive={result.naive.sharpe_ratio} ml={result.ml.sharpe_ratio} />
                <MetricRow label="Avg Trade PnL" naive={result.naive.avg_trade_pnl} ml={result.ml.avg_trade_pnl} format={v => `€${v.toFixed(2)}`} />
              </tbody>
            </table>
          </div>

          {/* Charts */}
          <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider">
                {activeView === 'equity' ? 'Equity Curves' : 'Monthly Returns Heatmap'}
              </h2>
              <div className="flex items-center gap-1">
                {(['equity', 'monthly'] as const).map(v => (
                  <button
                    key={v}
                    onClick={() => setActiveView(v)}
                    className={clsx(
                      'px-2.5 py-1 rounded text-[9px] font-mono uppercase transition-all',
                      activeView === v
                        ? 'bg-[#2196f3]/10 text-[#2196f3] border border-[#2196f3]/40'
                        : 'text-[#4a5568] hover:text-[#8892b0] border border-transparent'
                    )}
                  >
                    {v === 'equity' ? 'Equity' : 'Monthly'}
                  </button>
                ))}
              </div>
            </div>

            {activeView === 'equity' ? (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={equityData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="mlGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00d4aa" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#00d4aa" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="naiveGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8892b0" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#8892b0" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4a" />
                  <XAxis dataKey="time" tick={{ fill: '#4a5568', fontSize: 9, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={{ stroke: '#1e2d4a' }} interval={4} />
                  <YAxis tick={{ fill: '#4a5568', fontSize: 9, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} tickFormatter={v => `€${v}`} width={52} />
                  <Tooltip
                    contentStyle={{ background: '#141b2d', border: '1px solid #1e2d4a', borderRadius: 6, fontSize: 11, fontFamily: 'JetBrains Mono' }}
                    labelStyle={{ color: '#8892b0' }}
                    formatter={(v: number, name: string) => [`€${v.toFixed(2)}`, name === 'ml' ? 'ML' : 'Naive']}
                  />
                  <Legend formatter={(v) => v === 'ml' ? 'ML Strategy' : 'Naive Strategy'} />
                  <Area type="monotone" dataKey="naive" stroke="#8892b0" strokeWidth={1.5} fill="url(#naiveGrad)" dot={false} />
                  <Area type="monotone" dataKey="ml" stroke="#00d4aa" strokeWidth={2} fill="url(#mlGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              /* Monthly heatmap */
              <div className="space-y-3">
                <div className="text-[9px] text-[#4a5568] font-mono uppercase">Naive Strategy</div>
                <div className="grid grid-cols-6 gap-1">
                  {naiveMonthly.map((m) => (
                    <div key={m.month} className="rounded p-2 text-center" style={{ backgroundColor: `${MONTH_COLORS(m.return_pct)}20`, border: `1px solid ${MONTH_COLORS(m.return_pct)}40` }}>
                      <div className="text-[9px] text-[#4a5568] font-mono">{m.month}</div>
                      <div className="text-[11px] font-mono font-semibold mt-0.5 tabular-nums" style={{ color: MONTH_COLORS(m.return_pct) }}>
                        {m.return_pct > 0 ? '+' : ''}{m.return_pct.toFixed(1)}%
                      </div>
                    </div>
                  ))}
                </div>
                <div className="text-[9px] text-[#4a5568] font-mono uppercase mt-2">ML Strategy</div>
                <div className="grid grid-cols-6 gap-1">
                  {mlMonthly.map((m) => (
                    <div key={m.month} className="rounded p-2 text-center" style={{ backgroundColor: `${MONTH_COLORS(m.return_pct)}20`, border: `1px solid ${MONTH_COLORS(m.return_pct)}40` }}>
                      <div className="text-[9px] text-[#4a5568] font-mono">{m.month}</div>
                      <div className="text-[11px] font-mono font-semibold mt-0.5 tabular-nums" style={{ color: MONTH_COLORS(m.return_pct) }}>
                        {m.return_pct > 0 ? '+' : ''}{m.return_pct.toFixed(1)}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Win rate + profit factor comparison bars */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Win rate */}
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-4">
              <h3 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider mb-4">Win Rate</h3>
              <div className="space-y-3">
                {[
                  { label: 'Naive', value: result.naive.win_rate, color: '#8892b0' },
                  { label: 'ML', value: result.ml.win_rate, color: '#00d4aa' }
                ].map(({ label, value, color }) => (
                  <div key={label}>
                    <div className="flex justify-between text-[10px] font-mono mb-1">
                      <span style={{ color }}>{label}</span>
                      <span className="text-[#e8eaf0]">{(value * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-2.5 bg-[#1e2d4a] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${value * 100}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-[9px] text-[#4a5568] font-mono">
                50% = break-even · ML improvement: +{((result.ml.win_rate - result.naive.win_rate) * 100).toFixed(1)}pp
              </div>
            </div>

            {/* Profit factor */}
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-4">
              <h3 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider mb-4">Profit Factor</h3>
              <div className="space-y-3">
                {[
                  { label: 'Naive', value: result.naive.profit_factor, max: 3, color: '#8892b0' },
                  { label: 'ML', value: result.ml.profit_factor, max: 3, color: '#00d4aa' }
                ].map(({ label, value, max, color }) => (
                  <div key={label}>
                    <div className="flex justify-between text-[10px] font-mono mb-1">
                      <span style={{ color }}>{label}</span>
                      <span className="text-[#e8eaf0]">{value.toFixed(2)}x</span>
                    </div>
                    <div className="h-2.5 bg-[#1e2d4a] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${Math.min(100, (value / max) * 100)}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-[9px] text-[#4a5568] font-mono">
                1.0 = break-even · &gt;2.0 = excellent · ML: {result.ml.profit_factor.toFixed(2)}x
              </div>
            </div>
          </div>
        </>
      )}

      {!result && !loading && (
        <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-12 text-center">
          <Play size={24} className="text-[#1e2d4a] mx-auto mb-3" />
          <div className="text-[#4a5568] text-xs font-mono">
            Select a date range and click Run Backtest to see results
          </div>
        </div>
      )}
    </div>
  )
}
