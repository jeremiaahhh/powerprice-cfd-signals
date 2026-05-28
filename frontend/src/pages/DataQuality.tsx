import React, { useEffect, useState, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import { RefreshCw, Database, AlertTriangle, CheckCircle, Clock, Download } from 'lucide-react'
import { format, parseISO, formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'
import { getDataQuality, triggerIngest, DataQuality as DataQualityType, DataSource } from '../api/client'

function generateMockDataQuality(): DataQualityType {
  const now = new Date()
  const ts = (offsetMin: number) => new Date(now.getTime() - offsetMin * 60000).toISOString()

  return {
    sources: {
      smard: {
        name: 'SMARD (Bundesnetzagentur)',
        last_update: ts(12),
        age_minutes: 12,
        is_fresh: true,
        is_warning: false,
        missing_fields: [],
        record_count: 24
      },
      entsoe: {
        name: 'ENTSO-E Transparency',
        last_update: ts(38),
        age_minutes: 38,
        is_fresh: false,
        is_warning: true,
        missing_fields: ['load_forecast_h+3', 'cross_border_flow_AT'],
        record_count: 18
      },
      openmeteo: {
        name: 'Open-Meteo (Weather)',
        last_update: ts(5),
        age_minutes: 5,
        is_fresh: true,
        is_warning: false,
        missing_fields: [],
        record_count: 72
      }
    },
    overall_health: 'warning',
    last_ingest: ts(5),
    age_timeline: [
      { source: 'SMARD', age_minutes: 12, timestamp: ts(12) },
      { source: 'ENTSO-E', age_minutes: 38, timestamp: ts(38) },
      { source: 'OpenMeteo', age_minutes: 5, timestamp: ts(5) }
    ]
  }
}

const FRESHNESS_CONFIG = {
  fresh: { color: '#00ff66', label: 'Fresh', bg: 'bg-[#00ff66]/10', border: 'border-[#00ff66]/40', dot: 'bg-[#00ff66]' },
  warning: { color: '#ffcc00', label: 'Stale', bg: 'bg-[#ffcc00]/10', border: 'border-[#ffcc00]/40', dot: 'bg-[#ffcc00]' },
  critical: { color: '#ff3366', label: 'Critical', bg: 'bg-[#ff3366]/10', border: 'border-[#ff3366]/40', dot: 'bg-[#ff3366]' }
}

function getFreshnessLevel(source: DataSource): keyof typeof FRESHNESS_CONFIG {
  if (source.age_minutes > 60) return 'critical'
  if (source.is_warning || source.age_minutes > 30) return 'warning'
  return 'fresh'
}

function SourceCard({
  source,
  key: _key,
  onIngest
}: {
  source: DataSource
  key?: string
  onIngest: (name: string) => void
}) {
  const level = getFreshnessLevel(source)
  const cfg = FRESHNESS_CONFIG[level]

  return (
    <div className={clsx('rounded-lg border-l-2 border bg-[#111111] p-4', cfg.border, 'border-[#1f1f1f]')}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Database size={14} className="text-[#9a9a9a] flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-[11px] font-mono font-semibold text-[#e8e8e8]">{source.name}</div>
            {source.record_count !== undefined && (
              <div className="text-[9px] text-[#555555] font-mono mt-0.5">{source.record_count} records</div>
            )}
          </div>
        </div>
        <span
          className={clsx(
            'flex items-center gap-1.5 px-2 py-0.5 rounded border text-[9px] font-mono font-semibold flex-shrink-0',
            cfg.bg, cfg.border
          )}
          style={{ color: cfg.color }}
        >
          <span className={clsx('w-1.5 h-1.5 rounded-full', cfg.dot, level === 'fresh' && 'animate-pulse')} />
          {cfg.label}
        </span>
      </div>

      <div className="space-y-1.5 text-[10px] font-mono">
        <div className="flex items-center justify-between">
          <span className="text-[#555555]">Last update</span>
          <span className="text-[#9a9a9a]">
            {formatDistanceToNow(parseISO(source.last_update), { addSuffix: true })}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#555555]">Data age</span>
          <span style={{ color: cfg.color }} className="font-semibold">
            {source.age_minutes}m
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#555555]">Timestamp</span>
          <span className="text-[#9a9a9a]">
            {format(parseISO(source.last_update), 'HH:mm dd-MMM')}
          </span>
        </div>
      </div>

      {/* Age bar */}
      <div className="mt-3">
        <div className="h-1 bg-[#1f1f1f] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${Math.min(100, (source.age_minutes / 60) * 100)}%`,
              backgroundColor: cfg.color
            }}
          />
        </div>
        <div className="flex justify-between text-[8px] text-[#555555] font-mono mt-0.5">
          <span>0m</span>
          <span>30m</span>
          <span>60m</span>
        </div>
      </div>

      {/* Missing fields */}
      {source.missing_fields.length > 0 && (
        <div className="mt-3 bg-[#ffcc00]/5 border border-[#ffcc00]/20 rounded px-2.5 py-2">
          <div className="flex items-center gap-1 mb-1.5">
            <AlertTriangle size={10} className="text-[#ffcc00]" />
            <span className="text-[9px] text-[#ffcc00] font-mono">Missing fields</span>
          </div>
          <div className="space-y-0.5">
            {source.missing_fields.map(f => (
              <div key={f} className="text-[9px] text-[#ffcc00]/70 font-mono">• {f}</div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={() => onIngest(source.name)}
        className="mt-3 w-full flex items-center justify-center gap-1.5 px-2 py-1.5 bg-[#0a0a0a] border border-[#1f1f1f] rounded text-[9px] font-mono text-[#9a9a9a] hover:text-[#e8e8e8] hover:border-[#00d4ff]/30 transition-all"
      >
        <Download size={10} />
        Trigger Ingest
      </button>
    </div>
  )
}

export default function DataQuality() {
  const [data, setData] = useState<DataQualityType | null>(null)
  const [loading, setLoading] = useState(true)
  const [ingestLoading, setIngestLoading] = useState<string | null>(null)
  const [ingestMsg, setIngestMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const load = useCallback(async () => {
    try {
      const d = await getDataQuality()
      setData(d)
      setError(null)
    } catch {
      setError('API offline — demo data')
      if (!data) setData(generateMockDataQuality())
    } finally {
      setLoading(false)
      setLastRefresh(new Date())
    }
  }, [data])

  useEffect(() => {
    load()
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [load])

  const handleIngest = useCallback(async (sourceName: string) => {
    setIngestLoading(sourceName)
    setIngestMsg(null)
    try {
      const res = await triggerIngest(sourceName)
      setIngestMsg(`Ingest triggered: ${res.message}`)
      await load()
    } catch {
      setIngestMsg(`Ingest triggered for ${sourceName} (demo mode)`)
      setTimeout(() => setData(prev => prev ? { ...prev, last_ingest: new Date().toISOString() } : null), 500)
    } finally {
      setIngestLoading(null)
      setTimeout(() => setIngestMsg(null), 4000)
    }
  }, [load])

  const handleIngestAll = async () => {
    await handleIngest('all')
  }

  const sources = data ? [
    { key: 'smard', src: data.sources.smard },
    { key: 'entsoe', src: data.sources.entsoe },
    { key: 'openmeteo', src: data.sources.openmeteo }
  ] : []

  const healthConfig = {
    healthy: { color: '#00ff66', label: 'Healthy', icon: <CheckCircle size={14} /> },
    warning: { color: '#ffcc00', label: 'Warning', icon: <AlertTriangle size={14} /> },
    critical: { color: '#ff3366', label: 'Critical', icon: <AlertTriangle size={14} /> }
  }

  const health = data?.overall_health ?? 'healthy'
  const hCfg = healthConfig[health]

  const chartData = data?.age_timeline.map(t => ({
    source: t.source,
    age: t.age_minutes
  })) ?? []

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e8e8e8] font-mono">Data Quality</h1>
          <p className="text-xs text-[#555555] font-mono mt-0.5">
            Monitor data freshness across all sources
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
            <span className="text-[10px] text-[#ffcc00] font-mono">{error}</span>
          )}
          <button
            onClick={handleIngestAll}
            disabled={!!ingestLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#00d4ff]/10 border border-[#00d4ff]/40 rounded text-[10px] text-[#00d4ff] hover:bg-[#00d4ff]/20 transition-all disabled:opacity-50 font-mono"
          >
            <Download size={11} className={clsx(ingestLoading && 'animate-bounce')} />
            Ingest All
          </button>
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

      {/* Overall health */}
      <div className={clsx(
        'flex items-center justify-between rounded-lg border px-4 py-3',
        health === 'healthy' ? 'bg-[#00ff66]/5 border-[#00ff66]/30' :
        health === 'warning' ? 'bg-[#ffcc00]/5 border-[#ffcc00]/30' :
        'bg-[#ff3366]/5 border-[#ff3366]/30'
      )}>
        <div className="flex items-center gap-3">
          <span style={{ color: hCfg.color }}>{hCfg.icon}</span>
          <div>
            <div className="text-[11px] font-mono font-semibold" style={{ color: hCfg.color }}>
              Overall Health: {hCfg.label.toUpperCase()}
            </div>
            {data?.last_ingest && (
              <div className="text-[9px] text-[#555555] font-mono mt-0.5">
                Last ingest: {formatDistanceToNow(parseISO(data.last_ingest), { addSuffix: true })}
              </div>
            )}
          </div>
        </div>
        {ingestMsg && (
          <div className="flex items-center gap-1.5 text-[10px] text-[#00ff66] font-mono">
            <CheckCircle size={11} />
            {ingestMsg}
          </div>
        )}
      </div>

      {/* Source cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {sources.map(({ key, src }) => (
          <SourceCard
            key={key}
            source={src}
            onIngest={handleIngest}
          />
        ))}
      </div>

      {/* Age timeline chart */}
      <div className="bg-[#111111] border border-[#1f1f1f] rounded-lg p-4">
        <div className="mb-4">
          <h2 className="text-xs font-semibold text-[#e8e8e8] font-mono uppercase tracking-wider">
            Data Age by Source
          </h2>
          <p className="text-[10px] text-[#555555] font-mono mt-0.5">
            Green ≤30m · Orange 30–60m · Red &gt;60m
          </p>
        </div>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, 60]}
              tick={{ fill: '#555555', fontSize: 9, fontFamily: 'JetBrains Mono' }}
              tickLine={false}
              axisLine={{ stroke: '#1f1f1f' }}
              tickFormatter={(v) => `${v}m`}
            />
            <YAxis
              type="category"
              dataKey="source"
              tick={{ fill: '#9a9a9a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
              tickLine={false}
              axisLine={false}
              width={72}
            />
            <Tooltip
              formatter={(v: number) => [`${v} minutes`, 'Age']}
              contentStyle={{ background: '#111111', border: '1px solid #1f1f1f', borderRadius: 6, fontSize: 11, fontFamily: 'JetBrains Mono' }}
              labelStyle={{ color: '#9a9a9a' }}
            />
            {/* Reference line at 30m */}
            <Bar dataKey="age" radius={[0, 4, 4, 0]} maxBarSize={28}>
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.age > 60 ? '#ff3366' : entry.age > 30 ? '#ffcc00' : '#00ff66'}
                  fillOpacity={0.8}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Data field coverage */}
      {data && (
        <div className="bg-[#111111] border border-[#1f1f1f] rounded-lg p-4">
          <h2 className="text-xs font-semibold text-[#e8e8e8] font-mono uppercase tracking-wider mb-4">
            Field Coverage
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {sources.map(({ key, src }) => (
              <div key={key} className="bg-[#0a0a0a] rounded p-3">
                <div className="text-[9px] text-[#555555] font-mono uppercase mb-2">{src.name.split(' ')[0]}</div>
                {src.missing_fields.length === 0 ? (
                  <div className="flex items-center gap-1.5 text-[10px] text-[#00ff66] font-mono">
                    <CheckCircle size={11} />
                    All fields present
                  </div>
                ) : (
                  <div className="space-y-1">
                    {src.missing_fields.map(f => (
                      <div key={f} className="flex items-center gap-1.5 text-[10px] text-[#ff3366] font-mono">
                        <AlertTriangle size={10} />
                        {f}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
