import React from 'react'
import clsx from 'clsx'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

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

const BORDER_COLORS = {
  green: 'border-l-[#00d4aa]',
  red: 'border-l-[#ff4757]',
  yellow: 'border-l-[#ffa726]',
  blue: 'border-l-[#2196f3]',
  purple: 'border-l-[#9c27b0]',
  default: 'border-l-[#1e2d4a]'
}

const ICON_BG = {
  green: 'bg-[#00d4aa]/10 text-[#00d4aa]',
  red: 'bg-[#ff4757]/10 text-[#ff4757]',
  yellow: 'bg-[#ffa726]/10 text-[#ffa726]',
  blue: 'bg-[#2196f3]/10 text-[#2196f3]',
  purple: 'bg-[#9c27b0]/10 text-[#9c27b0]',
  default: 'bg-[#1e2d4a]/30 text-[#8892b0]'
}

const TREND_COLORS = {
  up: 'text-[#00d4aa]',
  down: 'text-[#ff4757]',
  neutral: 'text-[#8892b0]'
}

function formatNumber(value: string | number): string {
  if (typeof value === 'string') return value
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
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
  icon,
  subtitle,
  loading = false,
  size = 'md'
}: KPICardProps) {
  const TrendIcon =
    trend === 'up' ? TrendingUp :
    trend === 'down' ? TrendingDown :
    Minus

  return (
    <div
      className={clsx(
        'relative rounded-lg border-l-2 border border-[#1e2d4a] bg-[#141b2d] transition-all duration-200 hover:border-[#1e2d4a]/80',
        BORDER_COLORS[color],
        size === 'sm' ? 'p-3' : size === 'lg' ? 'p-5' : 'p-4'
      )}
    >
      {loading ? (
        <div className="animate-pulse space-y-2">
          <div className="h-3 w-24 bg-[#1e2d4a] rounded" />
          <div className="h-7 w-32 bg-[#1e2d4a] rounded" />
          <div className="h-2.5 w-16 bg-[#1e2d4a] rounded" />
        </div>
      ) : (
        <>
          {/* Header row */}
          <div className="flex items-start justify-between mb-2">
            <span
              className={clsx(
                'font-mono text-[#8892b0] uppercase tracking-wider',
                size === 'sm' ? 'text-[9px]' : 'text-[10px]'
              )}
            >
              {title}
            </span>
            {icon && (
              <div
                className={clsx(
                  'flex items-center justify-center rounded',
                  size === 'sm' ? 'w-6 h-6' : 'w-7 h-7',
                  ICON_BG[color]
                )}
              >
                {icon}
              </div>
            )}
          </div>

          {/* Value */}
          <div
            className={clsx(
              'font-mono font-semibold text-[#e8eaf0] tabular-nums leading-none',
              size === 'sm' ? 'text-lg' : size === 'lg' ? 'text-3xl' : 'text-2xl'
            )}
          >
            {formatNumber(value)}
            {unit && (
              <span className={clsx('font-normal text-[#8892b0] ml-1', size === 'sm' ? 'text-xs' : 'text-sm')}>
                {unit}
              </span>
            )}
          </div>

          {/* Footer: change + subtitle */}
          <div className="flex items-center justify-between mt-2">
            {subtitle && (
              <span className="text-[10px] text-[#4a5568] font-mono truncate max-w-[70%]">{subtitle}</span>
            )}
            {change !== undefined && (
              <div className={clsx('flex items-center gap-1 text-[10px] font-mono ml-auto', TREND_COLORS[trend])}>
                <TrendIcon size={11} />
                <span>{change > 0 ? '+' : ''}{change.toFixed(2)}</span>
              </div>
            )}
            {change === undefined && trend !== 'neutral' && (
              <div className={clsx('flex items-center gap-1 text-[10px] font-mono ml-auto', TREND_COLORS[trend])}>
                <TrendIcon size={11} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
