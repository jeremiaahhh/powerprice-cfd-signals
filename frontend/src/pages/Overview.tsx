import React, { useEffect, useState, useCallback } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { format, parseISO, subHours } from 'date-fns'
import clsx from 'clsx'
import KPICard from '../components/KPICard'
import SignalCard from '../components/SignalCard'
import useSignal from '../hooks/useSignal'
import { getPriceHistory, PriceHistory } from '../api/client'

// Mock data fallback if API unreachable
function generateMockPriceHistory(): PriceHistory {
  const now = new Date()
  const timestamps: string[] = []
  const prices: number[] = []
  for (let i = 23; i >= 0; i--) {
    timestamps.push(subHours(now, i).toISOString())
    const base = -10 + Math.sin(i * 0.5) * 15
    prices.push(parseFloat((base + (Math.random() - 0.5) * 8).toFixed(2)))
  }
  return { timestamps, prices }
}

interface ChartPoint {
  time: string
  price: number
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const price = payload[0].value as number
    return (
      <div className="bg-term-bg border border-term-border-strong px-2 py-1.5 text-2xs">
        <div className="text-text-muted uppercase tracking-wider mb-0.5">{label}</div>
        <div className={clsx('font-semibold tabular-nums', price < 0 ? 'text-bear' : 'text-bull')}>
          {price.toFixed(2)} EUR/MWh
        </div>
      </div>
    )
  }
  return null
}

export default function Overview() {
  const { signal, loading: signalLoading, error, lastRefresh, refresh } = useSignal({
    autoRefresh: true,
    intervalMs: 30_000,
  })

  const [priceHistory, setPriceHistory] = useState<ChartPoint[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const data = await getPriceHistory(24)
      const points = data.timestamps.map((ts, i) => ({
        time: format(parseISO(ts), 'HH:mm'),
        price: data.prices[i],
      }))
      setPriceHistory(points)
    } catch {
      const mock = generateMockPriceHistory()
      setPriceHistory(mock.timestamps.map((ts, i) => ({
        time: format(parseISO(ts), 'HH:mm'),
        price: mock.prices[i],
      })))
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHistory()
    const timer = setInterval(loadHistory, 30_000)
    return () => clearInterval(timer)
  }, [loadHistory])

  const handleRefresh = () => {
    refresh()
    loadHistory()
  }

  const currentPrice = signal?.current_price ?? 0
  const priceColor: 'green' | 'yellow' | 'red' =
    currentPrice < 0 ? 'red' : currentPrice < 20 ? 'yellow' : 'green'
  const minPrice = priceHistory.length ? Math.min(...priceHistory.map(p => p.price)) : 0
  const maxPrice = priceHistory.length ? Math.max(...priceHistory.map(p => p.price)) : 0
  const hasNegative = priceHistory.some(p => p.price < 0)

  return (
    <div className="space-y-4">
      {/* ============ HEADER ============ */}
      <div className="flex items-center justify-between border-b border-term-border pb-2">
        <div>
          <h1 className="text-2xs uppercase tracking-[0.16em] text-amber font-semibold">
            OVR · MARKET OVERVIEW
          </h1>
          <p className="text-3xs text-text-muted uppercase tracking-wider mt-0.5">
            German Day-Ahead · EPEX SPOT · DE-LU
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-3xs text-text-muted uppercase tracking-wider">
              UPD {format(lastRefresh, 'HH:mm:ss')}
            </span>
          )}
          {error && (
            <span className="text-3xs text-warn bg-warn/10 px-1.5 py-0.5 border border-warn/30 uppercase tracking-wider">
              DEMO MODE
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={signalLoading}
            className={clsx(
              'px-2.5 py-1 text-3xs uppercase tracking-wider border transition-colors disabled:opacity-50',
              'bg-term-panel border-term-border-strong text-text-secondary',
              'hover:text-amber hover:border-amber',
              signalLoading && 'term-blink',
            )}
          >
            REFRESH
          </button>
        </div>
      </div>

      {/* ============ KPI GRID ============ */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
        <KPICard
          title="Current Price"
          value={currentPrice.toFixed(2)}
          unit="EUR/MWh"
          trend={currentPrice < 0 ? 'down' : 'up'}
          color={priceColor}
          loading={signalLoading}
        />
        <KPICard
          title="P(Negative)"
          value={signal ? `${(signal.p_negative * 100).toFixed(0)}%` : '—'}
          trend={signal && signal.p_negative > 0.5 ? 'down' : 'neutral'}
          color={signal && signal.p_negative > 0.6 ? 'red' : signal && signal.p_negative > 0.4 ? 'yellow' : 'green'}
          subtitle="Neg. price prob."
          loading={signalLoading}
        />
        <KPICard
          title="P(Rebound)"
          value={signal ? `${(signal.p_rebound * 100).toFixed(0)}%` : '—'}
          trend={signal && signal.p_rebound > 0.5 ? 'up' : 'neutral'}
          color={signal && signal.p_rebound > 0.6 ? 'green' : 'yellow'}
          subtitle="Recovery prob."
          loading={signalLoading}
        />
        <KPICard
          title="Predicted Price"
          value={signal ? signal.predicted_price.toFixed(2) : '—'}
          unit={signal ? 'EUR/MWh' : undefined}
          color="blue"
          subtitle="6H horizon"
          loading={signalLoading}
        />
        <KPICard
          title="Net Edge"
          value={signal ? `${signal.net_edge > 0 ? '+' : ''}${signal.net_edge.toFixed(2)}` : '—'}
          trend={signal && signal.net_edge > 0 ? 'up' : 'down'}
          color={signal && signal.net_edge > 0 ? 'green' : 'red'}
          subtitle="After all costs"
          loading={signalLoading}
        />
      </div>

      {/* ============ CHART + SIGNAL ============ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Chart */}
        <div className="lg:col-span-2 bg-term-panel border border-term-border">
          <div className="flex items-center justify-between px-3 py-2 border-b border-term-border">
            <div>
              <h2 className="text-2xs font-semibold text-text-primary uppercase tracking-wider">
                Price History · 24H
              </h2>
              <div className="flex items-center gap-3 mt-0.5">
                <span className="text-3xs text-text-muted uppercase tracking-wider">
                  MIN <span className={clsx('ml-0.5 tabular-nums', minPrice < 0 ? 'text-bear' : 'text-bull')}>
                    {minPrice.toFixed(2)}
                  </span>
                </span>
                <span className="text-3xs text-text-muted uppercase tracking-wider">
                  MAX <span className="ml-0.5 text-bull tabular-nums">{maxPrice.toFixed(2)}</span>
                </span>
                {hasNegative && (
                  <span className="text-3xs text-bear uppercase tracking-wider border border-bear/40 px-1.5 py-0.5">
                    NEGATIVE PRICES
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="p-3">
            {historyLoading ? (
              <div className="h-52 flex items-center justify-center text-text-muted text-2xs uppercase tracking-wider term-blink">
                Loading chart data…
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={priceHistory} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={hasNegative ? '#ff3366' : '#ffa500'} stopOpacity={0.30} />
                      <stop offset="95%" stopColor={hasNegative ? '#ff3366' : '#ffa500'} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1f1f1f" strokeDasharray="0" />
                  <XAxis
                    dataKey="time"
                    tick={{ fill: '#9a9a9a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                    tickLine={false}
                    axisLine={{ stroke: '#2a2a2a' }}
                    interval={3}
                  />
                  <YAxis
                    tick={{ fill: '#9a9a9a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}`}
                    width={44}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={0} stroke="#ff3366" strokeDasharray="3 3" strokeOpacity={0.5} />
                  <Area
                    type="monotone"
                    dataKey="price"
                    stroke={hasNegative ? '#ff3366' : '#ffa500'}
                    strokeWidth={1.5}
                    fill="url(#priceGradient)"
                    dot={false}
                    activeDot={{ r: 3, fill: hasNegative ? '#ff3366' : '#ffa500' }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Signal */}
        <div>
          <h2 className="text-2xs font-semibold text-text-primary uppercase tracking-wider mb-2 border-b border-term-border pb-1.5">
            Current Signal
          </h2>
          {signalLoading && !signal ? (
            <div className="bg-term-panel border border-term-border p-5 text-center text-text-muted text-2xs uppercase tracking-wider term-blink">
              Loading signal…
            </div>
          ) : signal ? (
            <SignalCard signal={signal} compact />
          ) : (
            <div className="bg-term-panel border border-term-border p-5 text-center text-text-muted text-2xs uppercase tracking-wider">
              No signal available
            </div>
          )}
        </div>
      </div>

      {/* ============ SIGNAL REASON STRIP ============ */}
      {signal && (
        <div className="bg-term-panel border border-term-border px-3 py-2">
          <div className="flex items-start gap-3">
            <span className="text-3xs text-text-muted uppercase tracking-wider shrink-0">
              SIGNAL REASON
            </span>
            <span className="text-2xs text-text-secondary leading-relaxed">
              {signal.reason}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
