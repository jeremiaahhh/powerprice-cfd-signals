import { useEffect, useState } from 'react'
import { getDaemonStatus, getRecentNotifications, getNotificationStats, NotificationEvent, NotificationStats, DaemonStatus } from '../api/client'

function StatusChip({ status }: { status: string }) {
  const isOk = status === 'sent' || status === 'ok' || status === 'success'
  const isFail = status === 'failed' || status === 'error'
  const cls = isOk
    ? 'bg-green-900/40 text-green-300 border-green-700'
    : isFail
    ? 'bg-red-900/40 text-red-300 border-red-700'
    : 'bg-yellow-900/40 text-yellow-300 border-yellow-700'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono border ${cls}`}>
      {status.toUpperCase()}
    </span>
  )
}

function EnabledBadge({ enabled }: { enabled: boolean }) {
  return enabled ? (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-900/40 text-green-300 border border-green-700">
      <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
      ENABLED
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-700 text-gray-400 border border-gray-600">
      <span className="w-2 h-2 rounded-full bg-gray-500" />
      DISABLED
    </span>
  )
}

export default function TelegramSettings() {
  const [daemonStatus, setDaemonStatus] = useState<DaemonStatus | null>(null)
  const [notifications, setNotifications] = useState<NotificationEvent[]>([])
  const [stats, setStats] = useState<NotificationStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState('')

  const fetchAll = async () => {
    try {
      const [d, n, s] = await Promise.all([
        getDaemonStatus(),
        getRecentNotifications(50),
        getNotificationStats(7),
      ])
      setDaemonStatus(d)
      setNotifications(Array.isArray(n) ? n : [])
      setStats(s)
      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to load notification data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 30_000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3" />
        Loading notification data...
      </div>
    </div>
  )

  if (error) return (
    <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
      Error: {error}
    </div>
  )

  const telegramEnabled = daemonStatus?.telegram_enabled ?? false
  const sentToday = daemonStatus?.telegram_sent_today ?? 0
  const successRate = stats && stats.total > 0 ? ((stats.sent / stats.total) * 100).toFixed(1) : '—'

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white font-mono">TELEGRAM NOTIFICATIONS</h1>
          <EnabledBadge enabled={telegramEnabled} />
        </div>
        <span className="text-xs text-gray-500">Updated {lastUpdate} · auto-refreshes 30s</span>
      </div>

      {!telegramEnabled && (
        <div className="bg-gray-700/40 border border-gray-600 rounded-lg px-4 py-2 text-gray-400 text-sm">
          Telegram is currently disabled. Configure <code className="text-gray-300">TELEGRAM_BOT_TOKEN</code> and <code className="text-gray-300">TELEGRAM_CHAT_ID</code> in the <code className="text-gray-300">.env</code> file to enable.
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total Sent (7d)', value: stats?.sent ?? '—' },
          { label: 'Failed (7d)', value: stats?.failed ?? '—' },
          { label: 'Sent Today', value: sentToday },
          { label: 'Success Rate (7d)', value: `${successRate}%` },
        ].map(kpi => (
          <div key={kpi.label} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-500 mb-1">{kpi.label}</div>
            <div className="text-2xl font-mono font-bold text-white">{String(kpi.value)}</div>
          </div>
        ))}
      </div>

      {stats?.last_sent_at && (
        <div className="text-xs text-gray-500">
          Last notification sent: <span className="text-gray-300">{new Date(stats.last_sent_at).toLocaleString()}</span>
        </div>
      )}

      {/* By-type breakdown */}
      {stats && Object.keys(stats.by_type).length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-sm font-mono text-gray-300 mb-3">BY EVENT TYPE (7d)</h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.by_type).map(([type, count]) => (
              <span key={type} className="px-2 py-1 bg-gray-700 rounded text-xs font-mono text-gray-300">
                {type}: <span className="text-white font-bold">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recent Notifications Table */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700">
          <h2 className="text-sm font-mono text-gray-300">RECENT NOTIFICATIONS</h2>
        </div>
        {notifications.length === 0 ? (
          <div className="px-4 py-6 text-center text-gray-500 text-sm">No notification records found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-700 text-gray-500 text-left">
                  <th className="px-4 py-2">Time</th>
                  <th className="px-4 py-2">Event Type</th>
                  <th className="px-4 py-2">Channel</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">Fingerprint</th>
                </tr>
              </thead>
              <tbody>
                {notifications.map(n => (
                  <tr key={n.id} className="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors">
                    <td className="px-4 py-2 font-mono text-gray-300 whitespace-nowrap">
                      {new Date(n.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 font-mono text-white">{n.event_type}</td>
                    <td className="px-4 py-2 text-gray-400">{n.channel}</td>
                    <td className="px-4 py-2">
                      <StatusChip status={n.status} />
                    </td>
                    <td className="px-4 py-2 font-mono text-gray-500 truncate max-w-[120px]" title={n.fingerprint ?? ''}>
                      {n.fingerprint ? n.fingerprint.slice(0, 16) + '…' : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="text-xs text-gray-600 italic">
        Note: Telegram bot token configured in .env file. Token and chat ID are never exposed via the API.
      </div>
    </div>
  )
}
