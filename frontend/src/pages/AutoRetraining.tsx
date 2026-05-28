import { useEffect, useState } from 'react'
import { getModelRegistry, getThresholdAnalysis, ModelRegistryStatus } from '../api/client'

function MetricRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-gray-700/50 last:border-0">
      <span className="text-xs text-gray-400">{label}</span>
      <span className="text-xs font-mono text-white">{value != null ? String(value) : '—'}</span>
    </div>
  )
}

function PromotionBadge({ promoted }: { promoted: boolean | undefined }) {
  if (promoted == null) return null
  return promoted ? (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-mono font-semibold bg-green-900/40 text-green-300 border border-green-700">PROMOTED</span>
  ) : (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-mono font-semibold bg-gray-700 text-gray-400 border border-gray-600">NOT PROMOTED</span>
  )
}

export default function AutoRetraining() {
  const [registry, setRegistry] = useState<ModelRegistryStatus | null>(null)
  const [threshold, setThreshold] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState('')

  const fetchAll = async () => {
    try {
      const [r, t] = await Promise.all([
        getModelRegistry(),
        getThresholdAnalysis(90),
      ])
      setRegistry(r)
      setThreshold(t)
      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to load retraining data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 60_000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3" />
        Loading retraining data...
      </div>
    </div>
  )

  if (error) return (
    <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
      Error: {error}
    </div>
  )

  const prod = registry?.production_metrics ?? {}
  const lastPromo = registry?.last_promotion ?? {}

  const fmtNum = (v: unknown, digits = 4): string => {
    if (v == null) return '—'
    const n = Number(v)
    return isNaN(n) ? String(v) : n.toFixed(digits)
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white font-mono">AUTO RETRAINING</h1>
        <span className="text-xs text-gray-500">Updated {lastUpdate} · auto-refreshes 60s</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Production Model */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-sm font-mono text-gray-300 mb-3">PRODUCTION MODEL METRICS</h2>
          {Object.keys(prod).length === 0 ? (
            <div className="text-gray-500 text-sm">No production model metrics recorded yet.</div>
          ) : (
            <div>
              <MetricRow label="AUC" value={fmtNum(prod['auc'])} />
              <MetricRow label="F1 Score" value={fmtNum(prod['f1'])} />
              <MetricRow label="Profit Factor" value={fmtNum(prod['profit_factor'], 3)} />
              <MetricRow label="Win Rate" value={prod['win_rate'] != null ? `${fmtNum(prod['win_rate'], 1)}%` : '—'} />
              <MetricRow label="Max Drawdown" value={prod['max_drawdown_pct'] != null ? `${fmtNum(prod['max_drawdown_pct'], 1)}%` : '—'} />
              <MetricRow label="Recorded At" value={prod['recorded_at'] ? new Date(String(prod['recorded_at'])).toLocaleString() : '—'} />
              {Object.keys(prod).filter(k => !['auc','f1','profit_factor','win_rate','max_drawdown_pct','recorded_at'].includes(k)).map(k => (
                <MetricRow key={k} label={k} value={fmtNum(prod[k])} />
              ))}
            </div>
          )}
        </div>

        {/* Candidate Summary */}
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-sm font-mono text-gray-300 mb-3">CANDIDATE MODELS</h2>
          <div className="text-xs text-gray-400 mb-2">
            Evaluated candidates: <span className="text-white font-mono font-bold">{registry?.candidate_count ?? '—'}</span>
          </div>
          {(registry?.last_candidates ?? []).length === 0 ? (
            <div className="text-gray-500 text-sm">No candidate evaluations recorded yet.</div>
          ) : (
            <div className="space-y-2">
              {(registry?.last_candidates ?? []).slice(0, 3).map((c, i) => (
                <div key={i} className="bg-gray-700/40 rounded p-2">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-400">Candidate #{i + 1}</span>
                    <PromotionBadge promoted={c['promoted'] as boolean | undefined} />
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 text-xs">
                    {Object.entries(c).filter(([k]) => k !== 'promoted').slice(0, 6).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-gray-500">{k}</span>
                        <span className="text-gray-300 font-mono">{fmtNum(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Last Promotion Decision */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-sm font-mono text-gray-300 mb-3">LAST PROMOTION DECISION</h2>
        {Object.keys(lastPromo).length === 0 ? (
          <div className="text-gray-500 text-sm">No promotion decisions recorded yet.</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(lastPromo).map(([k, v]) => (
              <div key={k}>
                <div className="text-xs text-gray-500 mb-0.5">{k}</div>
                {k === 'promoted' ? (
                  <PromotionBadge promoted={v as boolean | undefined} />
                ) : (
                  <div className="text-sm font-mono text-white">{String(v ?? '—')}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Threshold Analysis */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-sm font-mono text-gray-300 mb-1">THRESHOLD ANALYSIS (90d)</h2>
        <p className="text-xs text-gray-500 mb-3 italic">
          Advisory only — these are data-driven suggestions. Any threshold changes must be manually reviewed and deployed.
        </p>
        {threshold == null || threshold['status'] === 'error' || threshold['status'] === 'insufficient_data' ? (
          <div className="text-gray-500 text-sm">
            {threshold?.['message'] as string ?? threshold?.['status'] as string ?? 'No threshold analysis available.'}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { label: 'Optimal p_rebound', key: 'optimal_p_rebound' },
              { label: 'Optimal Net Edge', key: 'optimal_net_edge' },
              { label: 'Optimal PF', key: 'optimal_pf' },
            ].map(item => (
              <div key={item.key} className="bg-gray-700/40 rounded p-3">
                <div className="text-xs text-gray-500 mb-1">{item.label}</div>
                <div className="text-lg font-mono font-bold text-white">
                  {threshold[item.key] != null ? fmtNum(threshold[item.key], 3) : '—'}
                </div>
              </div>
            ))}
          </div>
        )}
        {threshold && Boolean(threshold['status']) && threshold['status'] !== 'error' && threshold['status'] !== 'insufficient_data' && (
          <div className="mt-3 text-xs text-gray-500">
            Status: <span className="text-gray-300 font-mono">{String(threshold['status'])}</span>
            {threshold['days_analyzed'] != null && <> · Days analyzed: <span className="text-gray-300">{String(threshold['days_analyzed'])}</span></>}
          </div>
        )}
      </div>
    </div>
  )
}
