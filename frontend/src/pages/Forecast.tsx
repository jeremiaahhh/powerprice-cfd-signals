import React, { useEffect, useState, useCallback } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Area, AreaChart, Cell, Legend
} from 'recharts'
import { RefreshCw, TrendingDown, TrendingUp, Clock } from 'lucide-react'
import { format, parseISO, addHours } from 'date-fns'
import clsx from 'clsx'
import { getForecast, Forecast as ForecastType } from '../api/client'

// Generate demo forecast data
function generateMockForecast(): ForecastType {
  const now = new Date()
  const points = Array.from({ length: 7 }, (_, i) => {
    const ts = addHours(now, i).toISOString()
    const base = -15 + i * 8
    const price = base + (Math.random() - 0.5) * 10
    const pNeg = Math.max(0, Math.min(1, 0.9 - i * 0.12 + (Math.random() - 0.5) * 0.1))
    return {
      timestamp: ts,
      price: parseFloat(price.toFixed(2)),
      p_negative: parseFloat(pNeg.toFixed(3)),
      lower_bound: parseFloat((price - 8).toFixed(2)),
      upper_bound: parseFloat((price + 8).toFixed(2))
    }
  })

  return {
    generated_at: now.toISOString(),
    horizon_hours: 6,
    points,
    p_rebound_overall: 0.74,
    expected_low: Math.min(...points.map(p => p.price)),
    expected_high: Math.max(...points.map(p => p.price))
  }
}

const PriceTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const price = payload[0]?.value as number
    const lower = payload[1]?.value as number
    const upper = payload[2]?.value as number
    return (
      <div className="bg-[#111111] border border-[#1f1f1f] rounded p-2.5 text-xs font-mono space-y-1">
        <div className="text-[#9a9a9a]">{label}</div>
        <div className={clsx('font-semibold', price < 0 ? 'text-[#ff3366]' : 'text-[#00ff66]')}>
          Price: €{price?.toFixed(2)}
        </div>
        {lower !== undefined && upper !== undefined && (
          <div className="text-[#555555] text-[10px]">
            Range: €{lower?.toFixed(2)} – €{upper?.toFixed(2)}
          </div>
        )}
      </div>
    )
  }
  return null
}

const ProbTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const val = payload[0]?.value as number
    return (
      <div className="bg-[#111111] border border-[#1f1f1f] rounded p-2.5 text-xs font-mono space-y-1">
        <div className="text-[#9a9a9a]">{label}</div>
        <div className={clsx('font-semibold', val > 0.5 ? 'text-[#ff3366]' : 'text-[#00ff66]')}>
          P(Negative): {(val * 100).toFixed(0)}%
        </div>
      </div>
    )
  }
  return null
}

export default function Forecast() {
  const [forecast, setForecast] = useState<ForecastType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getForecast(6)
      setForecast(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load forecast')
      setForecast(generateMockForecast())
    } finally {
      setLoading(false)
      setLastRefresh(new Date())
    }
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, 60000)
    return () => clearInterval(timer)
  }, [load])

  const priceChartData = forecast?.points.map(p => ({
    time: format(parseISO(p.timestamp), 'HH:mm'),
    price: p.price,
    lower: p.lower_bound,
    upper: p.upper_bound
  })) ?? []

  const probChartData = forecast?.points.map(p => ({
    time: format(parseISO(p.timestamp), 'HH:mm'),
    pNeg: parseFloat((p.p_negative * 100).toFixed(1))
  })) ?? []

  const reboundPct = forecast ? (forecast.p_rebound_overall * 100).toFixed(0) : '—'
  const reboundColor = forecast && forecast.p_rebound_overall > 0.6 ? '#00ff66' : '#ffcc00'

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e8e8e8] font-mono">Price Forecast</h1>
          <p className="text-xs text-[#555555] font-mono mt-0.5">
            ML-based 6-hour ahead forecast · Updated every 60s
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-[10px] text-[#555555] font-mono flex items-center gap-1">
              <Clock size={10} />
              {format(lastRefresh, 'HH:mm:ss')}
            </span>
          )}
          {error && (
            <span className="text-[10px] text-[#ffcc00] font-mono bg-[#ffcc00]/10 px-2 py-0.5 rounded">
              Demo
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#111111] border border-[#1f1f1f] rounded text-[10px] text-[#9a9a9a] hover:text-[#e8e8e8] hover:border-[#00ff66]/30 transition-all disabled:opacity-50"
          >
            <RefreshCw size={11} className={clsx(loading && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-[#111111] border border-l-2 border-[#1f1f1f] border-l-[#00d4ff] rounded-lg p-3">
          <div className="text-[9px] text-[#555555] font-mono uppercase tracking-wider">Expected Low</div>
          <div className={clsx('text-xl font-mono font-semibold mt-1 tabular-nums', forecast && forecast.expected_low < 0 ? 'text-[#ff3366]' : 'text-[#e8e8e8]')}>
            {forecast ? `€${forecast.expected_low.toFixed(1)}` : '—'}
          </div>
          <div className="text-[9px] text-[#555555] font-mono mt-0.5">per MWh</div>
        </div>
        <div className="bg-[#111111] border border-l-2 border-[#1f1f1f] border-l-[#00ff66] rounded-lg p-3">
          <div className="text-[9px] text-[#555555] font-mono uppercase tracking-wider">Expected High</div>
          <div className="text-xl font-mono font-semibold mt-1 tabular-nums text-[#00ff66]">
            {forecast ? `€${forecast.expected_high.toFixed(1)}` : '—'}
          </div>
          <div className="text-[9px] text-[#555555] font-mono mt-0.5">per MWh</div>
        </div>
        <div className="bg-[#111111] border border-l-2 border-[#1f1f1f] border-l-[#ffcc00] rounded-lg p-3">
          <div className="text-[9px] text-[#555555] font-mono uppercase tracking-wider">P(Rebound) Overall</div>
          <div className="text-xl font-mono font-semibold mt-1 tabular-nums" style={{ color: reboundColor }}>
            {reboundPct}%
          </div>
          <div className="text-[9px] text-[#555555] font-mono mt-0.5">6h window</div>
        </div>
        <div className="bg-[#111111] border border-l-2 border-[#1f1f1f] border-l-[#ffa500] rounded-lg p-3">
          <div className="text-[9px] text-[#555555] font-mono uppercase tracking-wider">Horizon</div>
          <div className="text-xl font-mono font-semibold mt-1 tabular-nums text-[#e8e8e8]">
            {forecast?.horizon_hours ?? '—'}h
          </div>
          <div className="text-[9px] text-[#555555] font-mono mt-0.5">forecast window</div>
        </div>
      </div>

      {/* Price forecast chart */}
      <div className="bg-[#111111] border border-[#1f1f1f] rounded-lg p-4">
        <div className="mb-4">
          <h2 className="text-xs font-semibold text-[#e8e8e8] font-mono uppercase tracking-wider">
            Price Forecast — Next 6 Hours
          </h2>
          <p className="text-[10px] text-[#555555] font-mono mt-0.5">
            Shaded region = 80% confidence interval
          </p>
        </div>

        {loading && !forecast ? (
          <div className="h-52 flex items-center justify-center">
            <div className="text-[#555555] text-xs font-mono animate-pulse">Loading forecast…</div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={priceChartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="bandGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00d4ff" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#00d4ff" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" />
              <XAxis
                dataKey="time"
                tick={{ fill: '#555555', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                tickLine={false}
                axisLine={{ stroke: '#1f1f1f' }}
              />
              <YAxis
                tick={{ fill: '#555555', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `€${v}`}
                width={56}
              />
              <Tooltip content={<PriceTooltip />} />
              <ReferenceLine y={0} stroke="#ff3366" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: '€0', fill: '#ff3366', fontSize: 9 }} />
              <Line
                type="monotone"
                dataKey="upper"
                stroke="#00d4ff"
                strokeWidth={0}
                dot={false}
                strokeOpacity={0}
              />
              <Line
                type="monotone"
                dataKey="lower"
                stroke="#00d4ff"
                strokeWidth={0}
                dot={false}
                fill="url(#bandGrad)"
                strokeOpacity={0}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke="#00d4ff"
                strokeWidth={2}
                dot={{ r: 4, fill: '#00d4ff', strokeWidth: 0 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Negative probability bar chart */}
      <div className="bg-[#111111] border border-[#1f1f1f] rounded-lg p-4">
        <div className="mb-4">
          <h2 className="text-xs font-semibold text-[#e8e8e8] font-mono uppercase tracking-wider">
            Negative Price Probability by Hour
          </h2>
          <p className="text-[10px] text-[#555555] font-mono mt-0.5">
            Bars above 50% indicate elevated negative price risk
          </p>
        </div>

        {loading && !forecast ? (
          <div className="h-40 flex items-center justify-center">
            <div className="text-[#555555] text-xs font-mono animate-pulse">Loading…</div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={probChartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" vertical={false} />
              <XAxis
                dataKey="time"
                tick={{ fill: '#555555', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                tickLine={false}
                axisLine={{ stroke: '#1f1f1f' }}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: '#555555', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}%`}
                width={40}
              />
              <Tooltip content={<ProbTooltip />} />
              <ReferenceLine y={50} stroke="#ffcc00" strokeDasharray="4 4" strokeOpacity={0.6} label={{ value: '50%', fill: '#ffcc00', fontSize: 9 }} />
              <Bar dataKey="pNeg" radius={[3, 3, 0, 0]}>
                {probChartData.map((entry, index) => (
                  <Cell
                    key={index}
                    fill={entry.pNeg > 50 ? '#ff3366' : entry.pNeg > 30 ? '#ffcc00' : '#00ff66'}
                    fillOpacity={0.8}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Rebound gauge */}
      <div className="bg-[#111111] border border-[#1f1f1f] rounded-lg p-4">
        <h2 className="text-xs font-semibold text-[#e8e8e8] font-mono uppercase tracking-wider mb-4">
          Rebound Probability Gauge
        </h2>
        <div className="flex items-center gap-6">
          {/* Visual gauge */}
          <div className="relative flex-shrink-0">
            <svg width={160} height={90} viewBox="0 0 160 90">
              {/* Background arc */}
              <path
                d="M 15 80 A 65 65 0 0 1 145 80"
                fill="none"
                stroke="#1f1f1f"
                strokeWidth={12}
                strokeLinecap="round"
              />
              {/* Value arc */}
              {forecast && (() => {
                const pct = forecast.p_rebound_overall
                const angle = Math.PI * pct
                const x = 80 - 65 * Math.cos(angle)
                const y = 80 - 65 * Math.sin(angle)
                const largeArc = pct > 0.5 ? 1 : 0
                return (
                  <path
                    d={`M 15 80 A 65 65 0 ${largeArc} 1 ${x.toFixed(1)} ${y.toFixed(1)}`}
                    fill="none"
                    stroke={reboundColor}
                    strokeWidth={12}
                    strokeLinecap="round"
                    style={{ transition: 'all 0.6s ease' }}
                  />
                )
              })()}
              {/* Center text */}
              <text x="80" y="72" textAnchor="middle" fill={reboundColor} fontSize="22" fontWeight="600" fontFamily="JetBrains Mono">
                {reboundPct}%
              </text>
              <text x="80" y="88" textAnchor="middle" fill="#555555" fontSize="9" fontFamily="JetBrains Mono">
                P(REBOUND)
              </text>
            </svg>
          </div>

          {/* Interpretation */}
          <div className="flex-1 space-y-3">
            <div className="flex items-center gap-2">
              {forecast && forecast.p_rebound_overall > 0.6 ? (
                <TrendingUp size={16} className="text-[#00ff66]" />
              ) : (
                <TrendingDown size={16} className="text-[#ffcc00]" />
              )}
              <span className="text-sm font-mono font-semibold" style={{ color: reboundColor }}>
                {forecast && forecast.p_rebound_overall > 0.7 ? 'Strong rebound likely'
                  : forecast && forecast.p_rebound_overall > 0.5 ? 'Moderate rebound expected'
                  : 'Weak rebound signal'}
              </span>
            </div>
            <div className="space-y-1.5 text-[11px] font-mono text-[#9a9a9a]">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#00ff66] flex-shrink-0" />
                Above 70% = Strong ENTER signal
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#ffcc00] flex-shrink-0" />
                50–70% = WATCH for entry
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#ff3366] flex-shrink-0" />
                Below 50% = NO TRADE
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
