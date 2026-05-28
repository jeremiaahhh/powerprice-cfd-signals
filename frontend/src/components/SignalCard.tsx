import React from 'react'
import clsx from 'clsx'
import { AlertTriangle, TrendingUp, Eye, TrendingDown, Ban, ShieldAlert } from 'lucide-react'
import { Signal, SignalAction } from '../api/client'
import { format, parseISO } from 'date-fns'

interface SignalCardProps {
  signal: Signal
  compact?: boolean
}

const ACTION_CONFIG: Record<SignalAction, {
  label: string
  color: string
  bg: string
  border: string
  glow: string
  icon: React.ReactNode
}> = {
  ENTER: {
    label: 'ENTER LONG',
    color: 'text-[#00d4aa]',
    bg: 'bg-[#00d4aa]/10',
    border: 'border-[#00d4aa]/60',
    glow: 'shadow-[0_0_20px_rgba(0,212,170,0.15)]',
    icon: <TrendingUp size={14} />
  },
  WATCH: {
    label: 'WATCH',
    color: 'text-[#ffa726]',
    bg: 'bg-[#ffa726]/10',
    border: 'border-[#ffa726]/40',
    glow: '',
    icon: <Eye size={14} />
  },
  EXIT: {
    label: 'EXIT / CLOSE',
    color: 'text-[#ff4757]',
    bg: 'bg-[#ff4757]/10',
    border: 'border-[#ff4757]/40',
    glow: '',
    icon: <TrendingDown size={14} />
  },
  NO_TRADE: {
    label: 'NO TRADE',
    color: 'text-[#4a5568]',
    bg: 'bg-[#4a5568]/10',
    border: 'border-[#4a5568]/30',
    glow: '',
    icon: <Ban size={14} />
  },
  RISK: {
    label: 'HIGH RISK',
    color: 'text-[#ff4757]',
    bg: 'bg-[#ff4757]/10',
    border: 'border-[#ff4757]/60',
    glow: 'shadow-[0_0_20px_rgba(255,71,87,0.15)]',
    icon: <ShieldAlert size={14} />
  }
}

function ConfidenceBar({ value, label }: { value: number; label: string }) {
  const pct = Math.min(100, Math.max(0, value * 100))
  const color = pct >= 70 ? '#00d4aa' : pct >= 50 ? '#ffa726' : '#ff4757'

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-[#8892b0] font-mono w-24 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-[#1e2d4a] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-[10px] font-mono tabular-nums w-10 text-right" style={{ color }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  )
}

export default function SignalCard({ signal, compact = false }: SignalCardProps) {
  const cfg = ACTION_CONFIG[signal.action]
  const isEnter = signal.action === 'ENTER'
  const netEdgeColor = signal.net_edge > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'

  return (
    <div
      className={clsx(
        'rounded-lg border bg-[#141b2d] transition-all duration-200',
        cfg.border,
        cfg.glow,
        isEnter && 'animate-pulse-border'
      )}
    >
      {/* Header */}
      <div className={clsx('flex items-center justify-between px-4 py-3 border-b border-[#1e2d4a] rounded-t-lg', cfg.bg)}>
        <div className="flex items-center gap-2">
          <span className={clsx('flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold font-mono border', cfg.color, cfg.border, cfg.bg)}>
            {cfg.icon}
            {cfg.label}
          </span>
          <span className="text-[10px] text-[#4a5568] font-mono">
            {format(parseISO(signal.timestamp), 'HH:mm dd-MMM')}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-[9px] text-[#4a5568] font-mono uppercase">Confidence</div>
            <div className={clsx('text-sm font-semibold font-mono tabular-nums', cfg.color)}>
              {(signal.confidence * 100).toFixed(0)}%
            </div>
          </div>
          <div className={clsx('w-10 h-10 rounded-full border-2 flex items-center justify-center text-xs font-bold font-mono', cfg.border, cfg.color)}>
            {(signal.confidence * 100).toFixed(0)}
          </div>
        </div>
      </div>

      {/* Body */}
      <div className={clsx('p-4', compact ? 'space-y-3' : 'space-y-4')}>
        {/* Price row */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0f1629] rounded p-2.5">
            <div className="text-[9px] text-[#4a5568] font-mono uppercase mb-1">Current Price</div>
            <div className="text-[#e8eaf0] font-mono font-semibold text-base tabular-nums">
              €{signal.current_price.toFixed(2)}
              <span className="text-[10px] text-[#8892b0] font-normal ml-1">/ MWh</span>
            </div>
          </div>
          <div className="bg-[#0f1629] rounded p-2.5">
            <div className="text-[9px] text-[#4a5568] font-mono uppercase mb-1">Predicted Price</div>
            <div className="text-[#2196f3] font-mono font-semibold text-base tabular-nums">
              €{signal.predicted_price.toFixed(2)}
              <span className="text-[10px] text-[#8892b0] font-normal ml-1">/ MWh</span>
            </div>
          </div>
        </div>

        {/* Probabilities */}
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-[#0f1629] rounded p-2 text-center">
            <div className="text-[9px] text-[#4a5568] font-mono uppercase mb-0.5">P(Negative)</div>
            <div className={clsx('text-sm font-mono font-semibold tabular-nums', signal.p_negative > 0.5 ? 'text-[#ff4757]' : 'text-[#00d4aa]')}>
              {(signal.p_negative * 100).toFixed(0)}%
            </div>
          </div>
          <div className="bg-[#0f1629] rounded p-2 text-center">
            <div className="text-[9px] text-[#4a5568] font-mono uppercase mb-0.5">P(Rebound)</div>
            <div className={clsx('text-sm font-mono font-semibold tabular-nums', signal.p_rebound > 0.5 ? 'text-[#00d4aa]' : 'text-[#ffa726]')}>
              {(signal.p_rebound * 100).toFixed(0)}%
            </div>
          </div>
          <div className="bg-[#0f1629] rounded p-2 text-center">
            <div className="text-[9px] text-[#4a5568] font-mono uppercase mb-0.5">Net Edge</div>
            <div className={clsx('text-sm font-mono font-semibold tabular-nums', netEdgeColor)}>
              {signal.net_edge > 0 ? '+' : ''}€{signal.net_edge.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Risk levels */}
        <div className="grid grid-cols-2 gap-2">
          <div className="flex items-center justify-between bg-[#0f1629] rounded px-3 py-2">
            <span className="text-[9px] text-[#4a5568] font-mono uppercase">Stop Loss</span>
            <span className="text-[#ff4757] text-xs font-mono font-semibold tabular-nums">€{signal.stop_loss.toFixed(2)}</span>
          </div>
          <div className="flex items-center justify-between bg-[#0f1629] rounded px-3 py-2">
            <span className="text-[9px] text-[#4a5568] font-mono uppercase">Take Profit</span>
            <span className="text-[#00d4aa] text-xs font-mono font-semibold tabular-nums">€{signal.take_profit.toFixed(2)}</span>
          </div>
        </div>

        {/* Confidence breakdown */}
        {signal.confidence_breakdown && !compact && (
          <div className="bg-[#0f1629] rounded p-3 space-y-2">
            <div className="text-[9px] text-[#4a5568] font-mono uppercase tracking-wider mb-2">Confidence Breakdown</div>
            <ConfidenceBar value={signal.confidence_breakdown.ml_model} label="ML Model" />
            <ConfidenceBar value={signal.confidence_breakdown.price_level} label="Price Level" />
            <ConfidenceBar value={signal.confidence_breakdown.momentum} label="Momentum" />
            <ConfidenceBar value={signal.confidence_breakdown.volume_signal} label="Volume" />
            <ConfidenceBar value={signal.confidence_breakdown.weather_factor} label="Weather" />
          </div>
        )}

        {/* Reason */}
        <div className="bg-[#0f1629] rounded px-3 py-2">
          <div className="text-[9px] text-[#4a5568] font-mono uppercase mb-1">Signal Reason</div>
          <p className="text-[11px] text-[#8892b0] font-mono leading-relaxed">{signal.reason}</p>
        </div>

        {/* Risk warnings */}
        {signal.risk_warnings && signal.risk_warnings.length > 0 && !compact && (
          <div className="bg-[#ff4757]/5 border border-[#ff4757]/20 rounded px-3 py-2 space-y-1">
            <div className="flex items-center gap-1.5 mb-1.5">
              <AlertTriangle size={11} className="text-[#ff4757]" />
              <span className="text-[9px] text-[#ff4757] font-mono uppercase tracking-wider">Risk Warnings</span>
            </div>
            {signal.risk_warnings.map((w, i) => (
              <div key={i} className="flex items-start gap-1.5">
                <span className="text-[#ff4757] text-[10px] mt-0.5">•</span>
                <span className="text-[10px] text-[#ff4757]/80 font-mono leading-snug">{w}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
