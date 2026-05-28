import React, { useEffect, useState, useCallback } from 'react'
import { Play, Square, RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Activity } from 'lucide-react'
import { format, parseISO, formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'
import {
  getPaperTradingStatus,
  startPaperTrading,
  stopPaperTrading,
  PaperTradingStatus,
  PaperTrade,
  PaperPosition,
  SignalAction
} from '../api/client'
import KPICard from '../components/KPICard'

const ACTION_COLORS: Record<SignalAction, string> = {
  ENTER: 'text-[#00d4aa]',
  WATCH: 'text-[#ffa726]',
  EXIT: 'text-[#ff4757]',
  NO_TRADE: 'text-[#4a5568]',
  RISK: 'text-[#ff4757]'
}

// Generate demo data
function generateMockStatus(): PaperTradingStatus {
  const now = new Date()
  const trades: PaperTrade[] = Array.from({ length: 12 }, (_, i) => {
    const pnl = (Math.random() - 0.35) * 50
    return {
      id: `trade-${i}`,
      opened_at: new Date(now.getTime() - (i + 1) * 3600000 * (Math.random() + 0.5)).toISOString(),
      closed_at: new Date(now.getTime() - i * 3600000).toISOString(),
      action: Math.random() > 0.3 ? 'ENTER' : 'WATCH',
      entry_price: -(Math.random() * 25 + 2),
      exit_price: Math.random() * 30 + 5,
      realized_pnl: parseFloat(pnl.toFixed(2)),
      size: 1,
      signal_confidence: parseFloat((0.5 + Math.random() * 0.45).toFixed(2)),
      exit_reason: pnl > 0 ? 'Take profit reached' : 'Stop loss triggered'
    }
  })

  const positions: PaperPosition[] = [
    {
      id: 'pos-1',
      opened_at: new Date(now.getTime() - 2700000).toISOString(),
      action: 'ENTER',
      entry_price: -12.5,
      current_price: 8.4,
      unrealized_pnl: 20.9,
      size: 1,
      stop_loss: -25,
      take_profit: 35
    }
  ]

  const wins = trades.filter(t => t.realized_pnl > 0).length
  const totalPnl = trades.reduce((s, t) => s + t.realized_pnl, 0)

  return {
    is_running: true,
    started_at: new Date(now.getTime() - 86400000 * 3).toISOString(),
    total_pnl: parseFloat(totalPnl.toFixed(2)),
    win_rate: wins / trades.length,
    total_trades: trades.length,
    avg_trade_pnl: parseFloat((totalPnl / trades.length).toFixed(2)),
    open_positions: positions,
    trade_journal: trades,
    signal_quality: {
      total_signals: 87,
      enter_signals: 38,
      watch_signals: 29,
      no_trade_signals: 20,
      avg_confidence: 0.69
    }
  }
}

export default function PaperTrading() {
  const [status, setStatus] = useState<PaperTradingStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await getPaperTradingStatus()
      setStatus(data)
      setError(null)
    } catch {
      setError('API offline — demo data')
      if (!status) setStatus(generateMockStatus())
    } finally {
      setLoading(false)
      setLastRefresh(new Date())
    }
  }, [status])

  useEffect(() => {
    load()
    const timer = setInterval(load, 10000)
    return () => clearInterval(timer)
  }, [load])

  const handleStart = async () => {
    setActionLoading(true)
    try {
      await startPaperTrading()
      await load()
    } catch {
      setStatus(prev => prev ? { ...prev, is_running: true } : null)
    } finally {
      setActionLoading(false)
    }
  }

  const handleStop = async () => {
    setActionLoading(true)
    try {
      await stopPaperTrading()
      await load()
    } catch {
      setStatus(prev => prev ? { ...prev, is_running: false } : null)
    } finally {
      setActionLoading(false)
    }
  }

  const isRunning = status?.is_running ?? false
  const totalPnl = status?.total_pnl ?? 0

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e8eaf0] font-mono">Paper Trading</h1>
          <p className="text-xs text-[#4a5568] font-mono mt-0.5">
            Simulated trading with live signals — no real money
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-[10px] text-[#4a5568] font-mono">
              {format(lastRefresh, 'HH:mm:ss')}
            </span>
          )}
          {error && (
            <span className="flex items-center gap-1 text-[10px] text-[#ffa726] font-mono">
              <AlertTriangle size={10} /> {error}
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#141b2d] border border-[#1e2d4a] rounded text-[10px] text-[#8892b0] hover:text-[#e8eaf0] hover:border-[#00d4aa]/30 transition-all disabled:opacity-50"
          >
            <RefreshCw size={11} className={clsx(loading && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* Status + controls */}
      <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <div className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded border font-mono text-sm font-semibold',
              isRunning
                ? 'bg-[#00d4aa]/10 border-[#00d4aa]/40 text-[#00d4aa]'
                : 'bg-[#4a5568]/10 border-[#4a5568]/30 text-[#4a5568]'
            )}>
              <Activity size={14} className={clsx(isRunning && 'animate-pulse')} />
              {isRunning ? 'RUNNING' : 'STOPPED'}
            </div>
            {status?.started_at && isRunning && (
              <span className="text-[10px] text-[#4a5568] font-mono">
                Running since {formatDistanceToNow(parseISO(status.started_at), { addSuffix: true })}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleStart}
              disabled={isRunning || actionLoading}
              className="flex items-center gap-2 px-4 py-2 bg-[#00d4aa]/10 border border-[#00d4aa]/40 rounded text-[11px] font-mono text-[#00d4aa] hover:bg-[#00d4aa]/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed font-semibold"
            >
              <Play size={12} />
              Start
            </button>
            <button
              onClick={handleStop}
              disabled={!isRunning || actionLoading}
              className="flex items-center gap-2 px-4 py-2 bg-[#ff4757]/10 border border-[#ff4757]/40 rounded text-[11px] font-mono text-[#ff4757] hover:bg-[#ff4757]/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed font-semibold"
            >
              <Square size={12} />
              Stop
            </button>
          </div>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KPICard
          title="Total PnL"
          value={`${totalPnl >= 0 ? '+' : ''}€${totalPnl.toFixed(2)}`}
          trend={totalPnl >= 0 ? 'up' : 'down'}
          color={totalPnl >= 0 ? 'green' : 'red'}
          icon={totalPnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          loading={loading && !status}
        />
        <KPICard
          title="Win Rate"
          value={status ? `${(status.win_rate * 100).toFixed(0)}%` : '—'}
          trend={status && status.win_rate > 0.5 ? 'up' : 'down'}
          color={status && status.win_rate > 0.5 ? 'green' : 'yellow'}
          loading={loading && !status}
        />
        <KPICard
          title="Total Trades"
          value={status?.total_trades ?? '—'}
          trend="neutral"
          color="blue"
          loading={loading && !status}
        />
        <KPICard
          title="Avg Trade"
          value={status ? `€${status.avg_trade_pnl.toFixed(2)}` : '—'}
          trend={status && status.avg_trade_pnl > 0 ? 'up' : 'down'}
          color={status && status.avg_trade_pnl > 0 ? 'green' : 'red'}
          loading={loading && !status}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Open positions */}
        <div className="lg:col-span-2 bg-[#141b2d] border border-[#1e2d4a] rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-[#1e2d4a] bg-[#0f1629] flex items-center justify-between">
            <h2 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider">Open Positions</h2>
            <span className="text-[10px] font-mono text-[#8892b0]">
              {status?.open_positions.length ?? 0} open
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-[#1e2d4a]">
                  {['Opened', 'Action', 'Entry', 'Current', 'Unrealized PnL', 'Stop', 'Target'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-[9px] text-[#4a5568] uppercase tracking-wider font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!status?.open_positions.length ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-6 text-center text-[#4a5568] text-[11px]">
                      No open positions
                    </td>
                  </tr>
                ) : (
                  status.open_positions.map((pos) => (
                    <tr key={pos.id} className="border-b border-[#1e2d4a]/50 hover:bg-[#0f1629] transition-colors">
                      <td className="px-3 py-2.5 text-[#8892b0] whitespace-nowrap">
                        {format(parseISO(pos.opened_at), 'MM-dd HH:mm')}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={clsx('text-[10px] font-semibold', ACTION_COLORS[pos.action])}>
                          {pos.action}
                        </span>
                      </td>
                      <td className={clsx('px-3 py-2.5 tabular-nums', pos.entry_price < 0 ? 'text-[#ff4757]' : 'text-[#e8eaf0]')}>
                        €{pos.entry_price.toFixed(2)}
                      </td>
                      <td className={clsx('px-3 py-2.5 tabular-nums', pos.current_price < 0 ? 'text-[#ff4757]' : 'text-[#e8eaf0]')}>
                        €{pos.current_price.toFixed(2)}
                      </td>
                      <td className={clsx('px-3 py-2.5 tabular-nums font-semibold', pos.unrealized_pnl >= 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]')}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}€{pos.unrealized_pnl.toFixed(2)}
                      </td>
                      <td className="px-3 py-2.5 text-[#ff4757] tabular-nums">€{pos.stop_loss.toFixed(2)}</td>
                      <td className="px-3 py-2.5 text-[#00d4aa] tabular-nums">€{pos.take_profit.toFixed(2)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Signal quality */}
        {status?.signal_quality && (
          <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-4">
            <h2 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider mb-4">Signal Quality</h2>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-[10px] text-[#8892b0] font-mono">Total Signals</span>
                <span className="text-[11px] text-[#e8eaf0] font-mono font-semibold">{status.signal_quality.total_signals}</span>
              </div>
              {[
                { label: 'ENTER signals', val: status.signal_quality.enter_signals, total: status.signal_quality.total_signals, color: '#00d4aa' },
                { label: 'WATCH signals', val: status.signal_quality.watch_signals, total: status.signal_quality.total_signals, color: '#ffa726' },
                { label: 'NO TRADE', val: status.signal_quality.no_trade_signals, total: status.signal_quality.total_signals, color: '#4a5568' }
              ].map(({ label, val, total, color }) => (
                <div key={label}>
                  <div className="flex justify-between text-[10px] font-mono mb-1">
                    <span className="text-[#8892b0]">{label}</span>
                    <span style={{ color }}>{val} ({((val / total) * 100).toFixed(0)}%)</span>
                  </div>
                  <div className="h-1.5 bg-[#1e2d4a] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${(val / total) * 100}%`, backgroundColor: color }}
                    />
                  </div>
                </div>
              ))}
              <div className="pt-2 border-t border-[#1e2d4a]">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-[#8892b0] font-mono">Avg Confidence</span>
                  <span className="text-[11px] text-[#2196f3] font-mono font-semibold">
                    {(status.signal_quality.avg_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Trade journal */}
      <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-[#1e2d4a] bg-[#0f1629] flex items-center justify-between">
          <h2 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider">Trade Journal</h2>
          <span className="text-[10px] font-mono text-[#8892b0]">{status?.trade_journal.length ?? 0} trades</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-[#1e2d4a]">
                {['Opened', 'Closed', 'Action', 'Entry', 'Exit', 'PnL', 'Confidence', 'Exit Reason'].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-[9px] text-[#4a5568] uppercase tracking-wider font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!status?.trade_journal.length ? (
                <tr>
                  <td colSpan={8} className="px-3 py-6 text-center text-[#4a5568] text-[11px]">
                    No trades recorded yet
                  </td>
                </tr>
              ) : (
                status.trade_journal.map((trade) => (
                  <tr key={trade.id} className="border-b border-[#1e2d4a]/50 hover:bg-[#0f1629] transition-colors">
                    <td className="px-3 py-2.5 text-[#8892b0] whitespace-nowrap">
                      {format(parseISO(trade.opened_at), 'MM-dd HH:mm')}
                    </td>
                    <td className="px-3 py-2.5 text-[#8892b0] whitespace-nowrap">
                      {format(parseISO(trade.closed_at), 'MM-dd HH:mm')}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={clsx('text-[10px] font-semibold', ACTION_COLORS[trade.action])}>
                        {trade.action}
                      </span>
                    </td>
                    <td className={clsx('px-3 py-2.5 tabular-nums', trade.entry_price < 0 ? 'text-[#ff4757]' : 'text-[#e8eaf0]')}>
                      €{trade.entry_price.toFixed(2)}
                    </td>
                    <td className={clsx('px-3 py-2.5 tabular-nums', trade.exit_price < 0 ? 'text-[#ff4757]' : 'text-[#e8eaf0]')}>
                      €{trade.exit_price.toFixed(2)}
                    </td>
                    <td className={clsx('px-3 py-2.5 tabular-nums font-semibold text-sm', trade.realized_pnl >= 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]')}>
                      {trade.realized_pnl >= 0 ? '+' : ''}€{trade.realized_pnl.toFixed(2)}
                    </td>
                    <td className="px-3 py-2.5 text-[#8892b0] tabular-nums">
                      {(trade.signal_confidence * 100).toFixed(0)}%
                    </td>
                    <td className="px-3 py-2.5 text-[#4a5568] max-w-[160px] truncate">
                      {trade.exit_reason}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
