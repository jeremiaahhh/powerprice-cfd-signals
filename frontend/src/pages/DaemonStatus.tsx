import { useEffect, useState } from 'react'
import { getDaemonStatus, getDaemonLogs, postDaemonStop, postDaemonStart, postDaemonRestart, DaemonStatus as DaemonStatusType } from '../api/client'

function StatusBadge({ running }: { running: boolean }) {
  if (running) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-900/40 text-green-300 border border-green-700">
        <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
        RUNNING
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-900/40 text-red-300 border border-red-700">
      <span className="w-2 h-2 rounded-full bg-red-400" />
      STOPPED
    </span>
  )
}

function SignalModeBadge({ mode }: { mode: string }) {
  const isNormal = mode === 'NORMAL'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono font-semibold ${
      isNormal ? 'bg-green-900/40 text-green-300 border border-green-700' : 'bg-orange-900/40 text-orange-300 border border-orange-700'
    }`}>
      {mode}
    </span>
  )
}

function KpiCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="text-xs text-gray-500 mb-2">{label}</div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  )
}

export default function DaemonStatus() {
  const [status, setStatus] = useState<DaemonStatusType | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState('')
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  const fetchAll = async () => {
    try {
      const [s, l] = await Promise.all([getDaemonStatus(), getDaemonLogs(50)])
      setStatus(s)
      setLogs(l.lines ?? [])
      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to load daemon status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 15_000)
    return () => clearInterval(interval)
  }, [])

  const handleAction = async (action: 'start' | 'stop' | 'restart') => {
    const labels: Record<string, string> = { start: 'Start', stop: 'Stop', restart: 'Restart' }
    if (!window.confirm(`${labels[action]} the signal daemon?`)) return
    try {
      setActionMsg('Sending command…')
      if (action === 'start') await postDaemonStart()
      else if (action === 'stop') await postDaemonStop()
      else await postDaemonRestart()
      setActionMsg(`${labels[action]} command sent.`)
      setTimeout(() => { setActionMsg(null); fetchAll() }, 2000)
    } catch (e: any) {
      setActionMsg(`Error: ${e.message}`)
      setTimeout(() => setActionMsg(null), 4000)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3" />
        Loading daemon status...
      </div>
    </div>
  )

  if (error) return (
    <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
      Error: {error}
    </div>
  )

  const s = status!

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white font-mono">SIGNAL DAEMON</h1>
          <StatusBadge running={s.running} />
        </div>
        <span className="text-xs text-gray-500">Updated {lastUpdate} · auto-refreshes 15s</span>
      </div>

      {actionMsg && (
        <div className="bg-blue-900/30 border border-blue-700 rounded-lg px-4 py-2 text-blue-300 text-sm">
          {actionMsg}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Status">
          <StatusBadge running={s.running} />
        </KpiCard>
        <KpiCard label="Cycle Count">
          <span className="text-2xl font-mono font-bold text-white">{s.cycle_count}</span>
        </KpiCard>
        <KpiCard label="Signal Mode">
          <SignalModeBadge mode={s.signal_mode} />
        </KpiCard>
        <KpiCard label="Telegram Sent Today">
          <span className="text-2xl font-mono font-bold text-white">{s.telegram_sent_today}</span>
          <span className="text-xs text-gray-500">{s.telegram_enabled ? 'enabled' : 'disabled'}</span>
        </KpiCard>
      </div>

      {/* Detail Grid */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700">
          <h2 className="text-sm font-mono text-gray-300">RUNTIME DETAILS</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-0 divide-x divide-y divide-gray-700">
          {[
            { label: 'PID', value: s.pid != null ? String(s.pid) : '—' },
            { label: 'Started At', value: s.started_at ? new Date(s.started_at).toLocaleString() : '—' },
            { label: 'Last Run', value: s.last_run_at ? new Date(s.last_run_at).toLocaleString() : '—' },
            { label: 'Next Run', value: s.next_run_at ? new Date(s.next_run_at).toLocaleString() : '—' },
            { label: 'Consecutive Errors', value: String(s.consecutive_errors) },
            { label: 'Last Signal', value: s.last_signal ?? '—' },
          ].map(item => (
            <div key={item.label} className="px-4 py-3">
              <div className="text-xs text-gray-500 mb-1">{item.label}</div>
              <div className="text-sm font-mono text-white">{item.value}</div>
            </div>
          ))}
        </div>
        {s.last_signal_at && (
          <div className="px-4 py-2 border-t border-gray-700 text-xs text-gray-500">
            Last signal at: <span className="text-gray-300">{new Date(s.last_signal_at).toLocaleString()}</span>
          </div>
        )}
        {s.last_error && (
          <div className="px-4 py-2 border-t border-gray-700 text-xs text-red-400">
            Last error: {s.last_error}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-sm font-mono text-gray-300 mb-3">DAEMON CONTROLS</h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => handleAction('start')}
            className="px-4 py-2 bg-green-700 hover:bg-green-600 text-white text-sm rounded font-semibold transition-colors"
          >
            Start Daemon
          </button>
          <button
            onClick={() => handleAction('stop')}
            className="px-4 py-2 bg-red-700 hover:bg-red-600 text-white text-sm rounded font-semibold transition-colors"
          >
            Stop Daemon
          </button>
          <button
            onClick={() => handleAction('restart')}
            className="px-4 py-2 bg-yellow-700 hover:bg-yellow-600 text-white text-sm rounded font-semibold transition-colors"
          >
            Restart
          </button>
          <button
            onClick={fetchAll}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-white text-sm rounded font-semibold transition-colors"
          >
            Refresh Now
          </button>
        </div>
        {s.stop_signal_pending && (
          <div className="mt-2 text-xs text-orange-400">Stop signal file is pending — daemon will halt at end of current cycle.</div>
        )}
      </div>

      {/* Logs */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-sm font-mono text-gray-300">RECENT LOGS (last 50 lines)</h2>
          <span className="text-xs text-gray-500">{logs.length} lines</span>
        </div>
        <pre className="bg-gray-900 text-green-300 text-xs font-mono p-4 overflow-y-auto max-h-80 leading-relaxed whitespace-pre-wrap break-all">
          {logs.length > 0 ? logs.join('\n') : 'No log lines available.'}
        </pre>
      </div>
    </div>
  )
}
