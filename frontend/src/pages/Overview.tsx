import React, { useEffect, useState, useCallback } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { RefreshCw, Zap, TrendingUp, TrendingDown, BarChart2, DollarSign } from 'lucide-react'
import { format, parseISO, subHours } from 'date-fns'
import clsx from 'clsx'
import KPICard from '../components/KPICard'
import SignalCard from '../components/SignalCard'
import useSignal from '../hooks/useSignal'
import { getPriceHistory, PriceHistory } from '../api/client'

// Generate mock price history when API is unavailable
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
      <div className="bg-[#141b2d] border border-[#1e2d4a] rounded p-2 text-xs font-mono">
        <div className="text-[#8892b0] mb-1">{label}</div>
        <div className={clsx('font-semibold', price < 0 ? 'text-[#ff4757]' : 'text-[#00d4aa]')}>
          €{price.toFixed(2)} / MWh
        </div>
      </div>
    )
  }
  return null
}

export default function Overview() {
  const { signal, loading: signalLoading, error, lastRefresh, refresh } = useSignal({
    autoRefresh: true,
    intervalMs: 30000
  })

  const [priceHistory, setPriceHistory] = useState<ChartPoint[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const data = await getPriceHistory(24)
      const points = data.timestamps.map((ts, i) => ({
        time: format(parseISO(ts), 'HH:mm'),
        price: data.prices[i]
      }))
      setPriceHistory(points)
    } catch {
      const mock = generateMockPriceHistory()
      setPriceHistory(mock.timestamps.map((ts, i) => ({
        time: format(parseISO(ts), 'HH:mm'),
        price: mock.prices[i]
      })))
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHistory()
    const timer = setInterval(loadHistory, 30000)
    return () => clearInterval(timer)
  }, [loadHistory])

  const handleRefresh = () => {
    refresh()
    loadHistory()
  }

  const currentPrice = signal?.current_price ?? 0
  const priceColor = currentPrice < 0 ? 'red' : currentPrice < 20 ? 'yellow' : 'green'
  const minPrice = priceHistory.length ? Math.min(...priceHistory.map(p => p.price)) : 0
  const maxPrice = priceHistory.length ? Math.max(...priceHistory.map(p => p.price)) : 0

  // Determine gradient for area chart (negative = red zone)
  const hasNegative = priceHistory.some(p => p.price < 0)

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e8eaf0] font-mono">Market Overview</h1>
          <p className="text-xs text-[#4a5568] font-mono mt-0.5">
            German Day-Ahead Power · EPEX SPOT
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-[10px] text-[#4a5568] font-mono">
              Updated {format(lastRefresh, 'HH:mm:ss')}
            </span>
          )}
          {error && (
            <span className="text-[10px] text-[#ffa726] font-mono bg-[#ffa726]/10 px-2 py-0.5 rounded">
              Demo Mode
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={signalLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#141b2d] border border-[#1e2d4a] rounded text-[10px] text-[#8892b0] hover:text-[#e8eaf0] hover:border-[#00d4aa]/30 transition-all disabled:opacity-50"
          >
            <RefreshCw size={11} className={clsx(signalLoading && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <KPICard
          title="Current Price"
          value={currentPrice.toFixed(2)}
          unit="€/MWh"
          trend={currentPrice < 0 ? 'down' : 'up'}
          color={priceColor as any}
          icon={<DollarSign size={14} />}
          loading={signalLoading}
        />
        <KPICard
          title="P(Negative)"
          value={signal ? `${(signal.p_negative * 100).toFixed(0)}%` : '—'}
          trend={signal && signal.p_negative > 0.5 ? 'down' : 'neutral'}
          color={signal && signal.p_negative > 0.6 ? 'red' : signal && signal.p_negative > 0.4 ? 'yellow' : 'green'}
          icon={<TrendingDown size={14} />}
          subtitle="Neg. price probability"
          loading={signalLoading}
        />
        <KPICard
          title="P(Rebound)"
          value={signal ? `${(signal.p_rebound * 100).toFixed(0)}%` : '—'}
          trend={signal && signal.p_rebound > 0.5 ? 'up' : 'neutral'}
          color={signal && signal.p_rebound > 0.6 ? 'green' : 'yellow'}
          icon={<TrendingUp size={14} />}
          subtitle="Recovery probability"
          loading={signalLoading}
        />
        <KPICard
          title="Predicted Price"
          value={signal ? `€${signal.predicted_price.toFixed(2)}` : '—'}
          trend="up"
          color="blue"
          icon={<BarChart2 size={14} />}
          subtitle={`6h horizon`}
          loading={signalLoading}
        />
        <KPICard
          title="Net Edge"
          value={signal ? `€${signal.net_edge.toFixed(2)}` : '—'}
          trend={signal && signal.net_edge > 0 ? 'up' : 'down'}
          color={signal && signal.net_edge > 0 ? 'green' : 'red'}
          icon={<Zap size={14} />}
          subtitle="After all costs"
          loading={signalLoading}
        />
      </div>

      {/* Lower section: chart + signal */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Price chart - 2/3 width */}
        <div className="lg:col-span-2 bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xs font-semibold text-[#e8eaf0] font-mono uppercase tracking-wider">
                Price History — Last 24h
              </h2>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-[10px] text-[#4a5568] font-mono">
                  Min: <span className={minPrice < 0 ? 'text-[#ff4757]' : 'text-[#00d4aa]'}>€{minPrice.toFixed(2)}</span>
                </span>
                <span className="text-[10px] text-[#4a5568] font-mono">
                  Max: <span className="text-[#00d4aa]">€{maxPrice.toFixed(2)}</span>
                </span>
                {hasNegative && (
                  <span className="text-[10px] text-[#ff4757] font-mono bg-[#ff4757]/10 px-1.5 py-0.5 rounded">
                    Negative prices detected
                  </span>
                )}
              </div>
            </div>
          </div>

          {historyLoading ? (
            <div className="h-52 flex items-center justify-center">
              <div className="text-[#4a5568] text-xs font-mono animate-pulse">Loading chart data…</div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={priceHistory} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={hasNegative ? '#ff4757' : '#00d4aa'} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={hasNegative ? '#ff4757' : '#00d4aa'} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4a" />
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#4a5568', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  tickLine={false}
                  axisLine={{ stroke: '#1e2d4a' }}
                  interval={3}
                />
                <YAxis
                  tick={{ fill: '#4a5568', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `€${v}`}
                  width={52}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={0} stroke="#ff4757" strokeDasharray="4 4" strokeOpacity={0.5} />
                <Area
                  type="monotone"
                  dataKey="price"
                  stroke={hasNegative ? '#ff4757' : '#00d4aa'}
                  strokeWidth={1.5}
                  fill="url(#priceGradient)"
                  dot={false}
                  activeDot={{ r: 3, fill: hasNegative ? '#ff4757' : '#00d4aa' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Current signal - 1/3 width */}
        <div>
          <h2 className="text-xs font-semibold text-[#e8eaf0] font-mono uppercase tracking-wider mb-3">
            Current Signal
          </h2>
          {signalLoading && !signal ? (
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-6 flex items-center justify-center">
              <div className="text-[#4a5568] text-xs font-mono animate-pulse">Loading signal…</div>
            </div>
          ) : signal ? (
            <SignalCard signal={signal} compact />
          ) : (
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-6 text-center">
              <div className="text-[#4a5568] text-xs font-mono">No signal available</div>
            </div>
          )}
        </div>
      </div>

      {/* Market context bar */}
      {signal && (
        <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg px-4 py-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] text-[#4a5568] font-mono uppercase tracking-wider">Signal Reason:</span>
            <span className="text-[11px] text-[#8892b0] font-mono">{signal.reason}</span>
          </div>
        </div>
      )}
    </div>
  )
}

