import React from 'react'
import clsx from 'clsx'

interface KPICardProps {
  title: string
  value: string | number
  unit?: string
  change?: number
  trend?: 'up' | 'down' | 'neutral'
  color?: 'green' | 'red' | 'yellow' | 'blue' | 'purple' | 'default'
  icon?: React.ReactNode
  subtitle?: string
  loading?: boolean
  size?: 'sm' | 'md' | 'lg'
}

// Terminal-style top-bar colour per semantic accent
const ACCENT = {
  green:   'border-t-bull',
  red:     'border-t-bear',
  yellow:  'border-t-warn',
  blue:    'border-t-info',
  purple:  'border-t-amber',
  default: 'border-t-term-border-strong',
}

const TREND_COLOR = {
  up:      'text-bull',
  down:    'text-bear',
  neutral: 'text-text-muted',
}

const TREND_GLYPH = {
  up:      '▲',
  down:    '▼',
  neutral: '–',
}

function formatNumber(value: string | number): string {
  if (typeof value === 'string') return value
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
  }
  if (Number.isInteger(value)) return value.toString()
  return value.toFixed(2)
}

export default function KPICard({
  title,
  value,
  unit,
  change,
  trend = 'neutral',
  color = 'default',
  subtitle,
  loading = false,
  size = 'md',
}: KPICardProps) {
  return (
    <div
      className={clsx(
        'bg-term-panel border border-term-border border-t-2',
        ACCENT[color],
        size === 'sm' ? 'p-2.5' : size === 'lg' ? 'p-4' : 'p-3',
      )}
    >
      {loading ? (
        <div className="space-y-2">
          <div className="h-2.5 w-20 bg-term-border-strong" />
          <div className="h-6 w-24 bg-term-border-strong" />
          <div className="h-2 w-14 bg-term-border-strong" />
        </div>
      ) : (
        <>
          {/* TITLE */}
          <div className="flex items-center justify-between">
            <span
              className={clsx(
                'text-text-secondary uppercase tracking-wider truncate',
                size === 'sm' ? 'text-3xs' : 'text-2xs',
              )}
            >
              {title}
            </span>
            {change !== undefined && (
              <span className={clsx('text-3xs font-semibold tabular-nums', TREND_COLOR[trend])}>
                {TREND_GLYPH[trend]} {change > 0 ? '+' : ''}{change.toFixed(2)}
              </span>
            )}
          </div>

          {/* VALUE */}
          <div
            className={clsx(
              'mt-1 font-semibold text-text-primary tabular-nums leading-none',
              size === 'sm' ? 'text-base' : size === 'lg' ? 'text-2xl' : 'text-xl',
            )}
          >
            {formatNumber(value)}
            {unit && (
              <span className="ml-1 text-text-secondary text-xs font-normal">
                {unit}
              </span>
            )}
          </div>

          {/* SUBTITLE */}
          {subtitle && (
            <div className="mt-1.5 text-3xs text-text-muted uppercase tracking-wider truncate">
              {subtitle}
            </div>
          )}
        </>
      )}
    </div>
  )
}
