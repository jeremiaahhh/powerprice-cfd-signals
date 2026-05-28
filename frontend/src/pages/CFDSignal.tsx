import React, { useEffect, useState, useCallback } from 'react'
import { RefreshCw, AlertTriangle, Clock } from 'lucide-react'
import { format, parseISO } from 'date-fns'
import clsx from 'clsx'
import SignalCard from '../components/SignalCard'
import useSignal from '../hooks/useSignal'
import { Signal, SignalAction } from '../api/client'

const ACTION_BADGE: Record<SignalAction, { label: string; cls: string }> = {
  ENTER: { label: 'ENTER', cls: 'bg-[#00d4aa]/10 text-[#00d4aa] border-[#00d4aa]/40' },
  WATCH: { label: 'WATCH', cls: 'bg-[#ffa726]/10 text-[#ffa726] border-[#ffa726]/40' },
  EXIT: { label: 'EXIT', cls: 'bg-[#ff4757]/10 text-[#ff4757] border-[#ff4757]/40' },
  NO_TRADE: { label: 'NO TRADE', cls: 'bg-[#4a5568]/10 text-[#4a5568] border-[#4a5568]/30' },
  RISK: { label: 'RISK', cls: 'bg-[#ff4757]/10 text-[#ff4757] border-[#ff4757]/60' }
}

function CostRow({ label, value, isTotal = false, isNeg = false }: {
  label: string; value: number; isTotal?: boolean; isNeg?: boolean
}) {
  return (
    <tr className={clsx('border-b border-[#1e2d4a]', isTotal && 'bg-[#0f1629]')}>
      <td className={clsx('px-3 py-2 text-[11px] font-mono', isTotal ? 'text-[#e8eaf0] font-semibold' : 'text-[#8892b0]')}>
        {label}
      </td>
      <td className={clsx('px-3 py-2 text-[11px] font-mono tabular-nums text-right', isTotal ? (isNeg ? 'text-[#ff4757]' : 'text-[#00d4aa]') : 'text-[#e8eaf0]', isTotal && 'font-semibold')}>
        {value > 0 ? '+' : ''}€{value.toFixed(2)}
      </td>
    </tr>
  )
}

function FeatureRow({ label, value }: { label: string; value: number }) {
  const pct = Math.min(100, Math.max(0, Math.abs(value) * 100))
  const positive = value >= 0

  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-[#1e2d4a]/50 last:border-0">
      <span className="text-[10px] text-[#8892b0] font-mono w-40 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-[#1e2d4a] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            backgroundColor: positive ? '#00d4aa' : '#ff4757'
          }}
        />
      </div>
      <span className={clsx('text-[10px] font-mono tabular-nums w-16 text-right', positive ? 'text-[#00d4aa]' : 'text-[#ff4757]')}>
        {value > 0 ? '+' : ''}{value.toFixed(3)}
      </span>
    </div>
  )
}

export default function CFDSignal() {
  const { signal, history, loading, error, lastRefresh, refresh } = useSignal({
    autoRefresh: true,
    intervalMs: 30000,
    includeHistory: true,
    historyLimit: 20
  })

  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true)

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e8eaf0] font-mono">CFD Signal</h1>
          <p className="text-xs text-[#4a5568] font-mono mt-0.5">
            Negative-price rebound strategy · German power market
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-[10px] text-[#4a5568] font-mono flex items-center gap-1">
              <Clock size={10} />
              {format(lastRefresh, 'HH:mm:ss')}
            </span>
          )}
          <label className="flex items-center gap-1.5 text-[10px] text-[#8892b0] font-mono cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefreshEnabled}
              onChange={(e) => setAutoRefreshEnabled(e.target.checked)}
              className="w-3 h-3 accent-[#00d4aa]"
            />
            Auto-refresh (30s)
          </label>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#141b2d] border border-[#1e2d4a] rounded text-[10px] text-[#8892b0] hover:text-[#e8eaf0] hover:border-[#00d4aa]/30 transition-all disabled:opacity-50"
          >
            <RefreshCw size={11} className={clsx(loading && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-[#ffa726]/10 border border-[#ffa726]/30 rounded text-[11px] text-[#ffa726] font-mono">
          <AlertTriangle size={12} />
          API unavailable — showing demo data. {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Main signal card */}
        <div>
          <h2 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider mb-3">
            Current Signal
          </h2>
          {loading && !signal ? (
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg h-64 flex items-center justify-center">
              <div className="text-[#4a5568] text-xs font-mono animate-pulse">Loading signal…</div>
            </div>
          ) : signal ? (
            <SignalCard signal={signal} />
          ) : (
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg p-8 text-center">
              <div className="text-[#4a5568] text-xs font-mono">No signal data available</div>
            </div>
          )}
        </div>

        {/* Right column: costs + features */}
        <div className="space-y-4">
          {/* Cost breakdown */}
          {signal?.cost_breakdown && (
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-[#1e2d4a] bg-[#0f1629]">
                <h3 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider">
                  Cost Breakdown
                </h3>
              </div>
              <table className="w-full">
                <tbody>
                  <CostRow label="Bid-Ask Spread" value={-signal.cost_breakdown.spread} />
                  <CostRow label="Slippage" value={-signal.cost_breakdown.slippage} />
                  <CostRow label="Financing / Overnight" value={-signal.cost_breakdown.financing} />
                  <CostRow label="Broker Markup" value={-signal.cost_breakdown.broker_markup} />
                  <CostRow label="Safety Buffer" value={-signal.cost_breakdown.safety_buffer} />
                  <CostRow label="Total Cost" value={-signal.cost_breakdown.total} isTotal isNeg />
                  <CostRow
                    label="Net Edge (after all costs)"
                    value={signal.cost_breakdown.net_edge}
                    isTotal
                    isNeg={signal.cost_breakdown.net_edge < 0}
                  />
                </tbody>
              </table>
            </div>
          )}

          {/* Feature importances */}
          {signal?.features && Object.keys(signal.features).length > 0 && (
            <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-[#1e2d4a] bg-[#0f1629]">
                <h3 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider">
                  Feature Contributions
                </h3>
              </div>
              <div className="px-4 py-3 max-h-56 overflow-y-auto scrollbar-thin">
                {Object.entries(signal.features)
                  .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
                  .slice(0, 15)
                  .map(([key, val]) => (
                    <FeatureRow
                      key={key}
                      label={key.replace(/_/g, ' ')}
                      value={val}
                    />
                  ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Signal history table */}
      <div className="bg-[#141b2d] border border-[#1e2d4a] rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-[#1e2d4a] bg-[#0f1629] flex items-center justify-between">
          <h3 className="text-[10px] font-mono text-[#4a5568] uppercase tracking-wider">Signal History</h3>
          <span className="text-[10px] text-[#4a5568] font-mono">Last 20 signals</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-[#1e2d4a]">
                {['Timestamp', 'Action', 'Confidence', 'Price', 'Predicted', 'P(Neg)', 'P(Reb)', 'Net Edge'].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-[9px] text-[#4a5568] uppercase tracking-wider font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-3 py-6 text-center text-[#4a5568]">
                    {loading ? 'Loading history…' : 'No signal history available'}
                  </td>
                </tr>
              ) : (
                history.map((s, i) => {
                  const badge = ACTION_BADGE[s.action]
                  return (
                    <tr key={s.id ?? i} className="border-b border-[#1e2d4a]/50 hover:bg-[#0f1629] transition-colors">
                      <td className="px-3 py-2 text-[#8892b0] whitespace-nowrap">
                        {format(parseISO(s.timestamp), 'MM-dd HH:mm')}
                      </td>
                      <td className="px-3 py-2">
                        <span className={clsx('px-1.5 py-0.5 rounded border text-[9px] font-semibold', badge.cls)}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-3 py-2 tabular-nums text-[#e8eaf0]">
                        {(s.confidence * 100).toFixed(0)}%
                      </td>
                      <td className={clsx('px-3 py-2 tabular-nums', s.current_price < 0 ? 'text-[#ff4757]' : 'text-[#e8eaf0]')}>
                        €{s.current_price.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-[#2196f3]">
                        €{s.predicted_price.toFixed(2)}
                      </td>
                      <td className={clsx('px-3 py-2 tabular-nums', s.p_negative > 0.5 ? 'text-[#ff4757]' : 'text-[#8892b0]')}>
                        {(s.p_negative * 100).toFixed(0)}%
                      </td>
                      <td className={clsx('px-3 py-2 tabular-nums', s.p_rebound > 0.5 ? 'text-[#00d4aa]' : 'text-[#8892b0]')}>
                        {(s.p_rebound * 100).toFixed(0)}%
                      </td>
                      <td className={clsx('px-3 py-2 tabular-nums font-semibold', s.net_edge > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]')}>
                        {s.net_edge > 0 ? '+' : ''}€{s.net_edge.toFixed(2)}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
