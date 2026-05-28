import { useEffect, useState } from 'react'
import { getDriftReport, DriftReport } from '../api/client'

function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    severity === 'HIGH' ? 'bg-red-900/40 text-red-300 border-red-700' :
    severity === 'MEDIUM' ? 'bg-yellow-900/40 text-yellow-300 border-yellow-700' :
    severity === 'LOW' ? 'bg-blue-900/40 text-blue-300 border-blue-700' :
    'bg-gray-700 text-gray-400 border-gray-600'
  return (
    <span className={`inline-block px-2.5 py-1 rounded text-xs font-mono font-semibold border ${cls}`}>
      {severity || 'NONE'}
    </span>
  )
}

function DriftBadge({ type }: { type: string }) {
  return (
    <span className="inline-block px-2 py-1 rounded bg-orange-900/30 text-orange-300 border border-orange-700 text-xs font-mono">
      {type}
    </span>
  )
}

export default function DriftMonitor() {
  const [report, setReport] = useState<DriftReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState('')
  const [expanded, setExpanded] = useState(false)

  const fetchReport = async () => {
    try {
      const r = await getDriftReport()
      setReport(r)
      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to load drift report')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchReport()
    const interval = setInterval(fetchReport, 300_000)
    return () => clearInterval(interval)
  }, [])

  const handleRunCheck = async () => {
    setChecking(true)
    try {
      await fetchReport()
    } finally {
      setChecking(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3" />
        Loading drift report...
      </div>
    </div>
  )

  if (error) return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white font-mono">DRIFT MONITOR</h1>
        <button
          onClick={handleRunCheck}
          className="px-4 py-2 bg-blue-700 hover:bg-blue-600 text-white text-sm rounded font-semibold transition-colors"
        >
          Retry
        </button>
      </div>
      <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
        Error: {error}
      </div>
    </div>
  )

  const r = report!

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white font-mono">DRIFT MONITOR</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Updated {lastUpdate} · auto-refreshes 5min</span>
          <button
            onClick={handleRunCheck}
            disabled={checking}
            className="px-4 py-2 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white text-sm rounded font-semibold transition-colors"
          >
            {checking ? 'Checking…' : 'Run Drift Check'}
          </button>
        </div>
      </div>

      {/* Drift Status Card */}
      <div className={`rounded-lg p-4 border ${
        r.has_drift
          ? r.severity === 'HIGH' ? 'bg-red-900/20 border-red-700' :
            r.severity === 'MEDIUM' ? 'bg-yellow-900/20 border-yellow-700' :
            'bg-orange-900/20 border-orange-700'
          : 'bg-green-900/10 border-green-700/40'
      }`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">Drift Detected</div>
              <span className={`text-lg font-mono font-bold ${r.has_drift ? 'text-red-400' : 'text-green-400'}`}>
                {r.has_drift ? 'YES' : 'NO'}
              </span>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">Severity</div>
              <SeverityBadge severity={r.severity} />
            </div>
          </div>
          <div className="text-xs text-gray-500">
            Checked: <span className="text-gray-300">{new Date(r.checked_at).toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Drift Types */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-sm font-mono text-gray-300 mb-3">DRIFT TYPES DETECTED</h2>
        {r.drift_types.length === 0 ? (
          <span className="text-gray-500 text-sm">No drift types detected — market conditions appear stable.</span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {r.drift_types.map(type => (
              <DriftBadge key={type} type={type} />
            ))}
          </div>
        )}
      </div>

      {/* Details */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <button
          onClick={() => setExpanded(e => !e)}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-700/30 transition-colors text-left"
        >
          <h2 className="text-sm font-mono text-gray-300">DRIFT DETAILS</h2>
          <span className="text-xs text-gray-500">{expanded ? '▲ collapse' : '▼ expand'}</span>
        </button>
        {expanded && (
          <div className="border-t border-gray-700">
            {Object.keys(r.details).length === 0 ? (
              <div className="px-4 py-4 text-gray-500 text-sm">No detailed breakdown available.</div>
            ) : (
              <pre className="bg-gray-900 text-green-300 text-xs font-mono p-4 overflow-x-auto whitespace-pre-wrap break-all max-h-80">
                {JSON.stringify(r.details, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>

      {/* Advisory Note */}
      {r.has_drift && (
        <div className="bg-gray-700/30 border border-gray-600 rounded-lg p-3 text-xs text-gray-400">
          <span className="font-semibold text-gray-300">Advisory:</span> Drift detected does not automatically trigger model retraining unless auto-retrain is enabled.
          Review the drift details above and consider running a manual retrain if severity is HIGH or multiple drift types are active.
        </div>
      )}
    </div>
  )
}
