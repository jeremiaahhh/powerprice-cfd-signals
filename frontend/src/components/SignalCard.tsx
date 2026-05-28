import React from 'react'
import clsx from 'clsx'
import { Signal, SignalAction } from '../api/client'
import { format, parseISO } from 'date-fns'

interface SignalCardProps {
  signal: Signal
  compact?: boolean
}

const ACTION_CONFIG: Record<SignalAction, {
  label: string
  color: string
  border: string
  bar: string
}> = {
  ENTER: {
    label: 'ENTER LONG',
    color: 'text-bull',
    border: 'border-bull',
    bar:   'bg-bull',
  },
  WATCH: {
    label: 'WATCH',
    color: 'text-warn',
    border: 'border-warn',
    bar:   'bg-warn',
  },
  EXIT: {
    label: 'EXIT / CLOSE',
    color: 'text-bear',
    border: 'border-bear',
    bar:   'bg-bear',
  },
  NO_TRADE: {
    label: 'NO TRADE',
    color: 'text-text-muted',
    border: 'border-term-border-strong',
    bar:   'bg-term-border-strong',
  },
  RISK: {
    label: 'HIGH RISK / BLOCKED',
    color: 'text-bear',
    border: 'border-bear',
    bar:   'bg-bear',
  },
}

function ConfidenceRow({ value, label }: { value: number; label: string }) {
  const pct = Math.min(100, Math.max(0, value * 100))
  const color =
    pct >= 70 ? 'bg-bull text-bull'
      : pct >= 50 ? 'bg-warn text-warn'
      : 'bg-bear text-bear'
  const [barColor, textColor] = color.split(' ')

  return (
    <div className="grid grid-cols-[100px_1fr_44px] items-center gap-2">
      <span className="text-3xs text-text-secondary uppercase tracking-wider truncate">
        {label}
      </span>
      <div className="h-1.5 bg-term-border">
        <div className={clsx('h-full', barColor)} style={{ width: `${pct}%` }} />
      </div>
      <span className={clsx('text-3xs font-semibold tabular-nums text-right', textColor)}>
        {pct.toFixed(0)}%
      </span>
    </div>
  )
}

function Cell({ label, value, valueClass }: {
  label: string
  value: React.ReactNode
  valueClass?: string
}) {
  return (
    <div className="flex flex-col bg-term-bg border border-term-border px-2.5 py-1.5">
      <span className="text-3xs text-text-muted uppercase tracking-wider">{label}</span>
      <span className={clsx('mt-0.5 text-sm font-semibold tabular-nums', valueClass || 'text-text-primary')}>
        {value}
      </span>
    </div>
  )
}

export default function SignalCard({ signal, compact = false }: SignalCardProps) {
  const cfg = ACTION_CONFIG[signal.action]
  const netEdgeColor = signal.net_edge > 0 ? 'text-bull' : 'text-bear'

  return (
    <div className={clsx('bg-term-panel border border-term-border border-l-2', cfg.border)}>
      {/* HEADER ROW */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-term-border">
        <div className="flex items-center gap-3">
          <span className={clsx('text-2xs font-semibold uppercase tracking-wider', cfg.color)}>
            {cfg.label}
          </span>
          <span className="text-3xs text-text-muted uppercase tracking-wider">
            {format(parseISO(signal.timestamp), 'yyyy-MM-dd HH:mm')}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-3xs text-text-muted uppercase tracking-wider">Confidence</span>
          <span className={clsx('text-base font-semibold tabular-nums', cfg.color)}>
            {(signal.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* BODY */}
      <div className={clsx('p-3 space-y-2.5', compact && 'space-y-2')}>
        {/* PRICE PAIR */}
        <div className="grid grid-cols-2 gap-2">
          <Cell
            label="Current Price"
            value={
              <>
                {signal.current_price.toFixed(2)}
                <span className="ml-1 text-3xs text-text-muted font-normal">EUR/MWh</span>
              </>
            }
          />
          <Cell
            label="Predicted Price"
            value={
              <>
                {signal.predicted_price.toFixed(2)}
                <span className="ml-1 text-3xs text-text-muted font-normal">EUR/MWh</span>
              </>
            }
            valueClass="text-info"
          />
        </div>

        {/* PROBABILITIES */}
        <div className="grid grid-cols-3 gap-2">
          <Cell
            label="P(Negative)"
            value={`${(signal.p_negative * 100).toFixed(0)}%`}
            valueClass={signal.p_negative > 0.5 ? 'text-bear' : 'text-bull'}
          />
          <Cell
            label="P(Rebound)"
            value={`${(signal.p_rebound * 100).toFixed(0)}%`}
            valueClass={signal.p_rebound > 0.5 ? 'text-bull' : 'text-warn'}
          />
          <Cell
            label="Net Edge"
            value={`${signal.net_edge > 0 ? '+' : ''}${signal.net_edge.toFixed(2)}`}
            valueClass={netEdgeColor}
          />
        </div>

        {/* RISK LEVELS */}
        <div className="grid grid-cols-2 gap-2">
          <Cell
            label="Stop Loss"
            value={signal.stop_loss.toFixed(2)}
            valueClass="text-bear"
          />
          <Cell
            label="Take Profit"
            value={signal.take_profit.toFixed(2)}
            valueClass="text-bull"
          />
        </div>

        {/* CONFIDENCE BREAKDOWN */}
        {signal.confidence_breakdown && !compact && (
          <div className="bg-term-bg border border-term-border p-2.5 space-y-1.5">
            <div className="text-3xs text-text-secondary uppercase tracking-wider mb-1">
              Confidence Breakdown
            </div>
            <ConfidenceRow value={signal.confidence_breakdown.ml_model}      label="ML Model" />
            <ConfidenceRow value={signal.confidence_breakdown.price_level}   label="Price Level" />
            <ConfidenceRow value={signal.confidence_breakdown.momentum}      label="Momentum" />
            <ConfidenceRow value={signal.confidence_breakdown.volume_signal} label="Volume" />
            <ConfidenceRow value={signal.confidence_breakdown.weather_factor} label="Weather" />
          </div>
        )}

        {/* REASON */}
        <div className="bg-term-bg border border-term-border px-2.5 py-1.5">
          <div className="text-3xs text-text-muted uppercase tracking-wider">Signal Reason</div>
          <p className="mt-1 text-2xs text-text-secondary leading-relaxed">
            {signal.reason}
          </p>
        </div>

        {/* RISK WARNINGS */}
        {signal.risk_warnings && signal.risk_warnings.length > 0 && !compact && (
          <div className="border border-bear/40 bg-bear/5 px-2.5 py-1.5 space-y-1">
            <div className="text-3xs text-bear uppercase tracking-wider font-semibold">
              Risk Warnings
            </div>
            {signal.risk_warnings.map((w, i) => (
              <div key={i} className="text-2xs text-bear/80 leading-snug">
                — {w}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
