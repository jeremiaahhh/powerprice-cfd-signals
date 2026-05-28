import React, { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  LayoutDashboard,
  TrendingUp,
  BarChart2,
  Calculator,
  FlaskConical,
  BookOpen,
  ShieldCheck,
  ShieldAlert,
  Battery,
  Zap,
  Wifi,
  WifiOff,
  AlertTriangle,
  Cpu,
  Send,
  Eye,
  RefreshCw,
  TrendingDown
} from 'lucide-react'
import clsx from 'clsx'
import { healthCheck } from '../api/client'
import { format } from 'date-fns'

interface NavItem {
  label: string
  path: string
  icon: React.ReactNode
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Overview', path: '/', icon: <LayoutDashboard size={18} /> },
  { label: 'CFD Signal', path: '/signal', icon: <TrendingUp size={18} /> },
  { label: 'Forecast', path: '/forecast', icon: <BarChart2 size={18} /> },
  { label: 'Cost Simulator', path: '/costs', icon: <Calculator size={18} /> },
  { label: 'Backtest', path: '/backtest', icon: <FlaskConical size={18} /> },
  { label: 'Paper Trading', path: '/paper', icon: <BookOpen size={18} /> },
  { label: 'Data Quality', path: '/data', icon: <ShieldCheck size={18} /> },
  { label: 'Battery', path: '/battery', icon: <Battery size={18} /> },
  { label: 'Tail Risk', path: '/tail-risk', icon: <ShieldAlert size={18} /> },
  { label: 'OOS Perf', path: '/signal-stability', icon: <BarChart2 size={18} /> },
  { label: 'Daemon', path: '/daemon', icon: <Cpu size={18} /> },
  { label: 'Telegram', path: '/telegram', icon: <Send size={18} /> },
  { label: 'Shadow Mode', path: '/shadow-mode', icon: <Eye size={18} /> },
  { label: 'Auto Retrain', path: '/auto-retraining', icon: <RefreshCw size={18} /> },
  { label: 'Drift Monitor', path: '/drift-monitor', icon: <TrendingDown size={18} /> },
]

export default function Layout() {
  const [now, setNow] = useState(new Date())
  const [connected, setConnected] = useState<boolean | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(tick)
  }, [])

  useEffect(() => {
    const check = async () => {
      try {
        await healthCheck()
        setConnected(true)
      } catch {
        setConnected(false)
      }
    }
    check()
    const interval = setInterval(check, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-[#0a0e1a]">
      {/* Sidebar */}
      <aside
        className={clsx(
          'flex flex-col border-r border-[#1e2d4a] bg-[#0f1629] transition-all duration-200',
          sidebarOpen ? 'w-52' : 'w-16'
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 py-4 border-b border-[#1e2d4a]">
          <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded bg-[#00d4aa]/10 border border-[#00d4aa]/30">
            <Zap size={16} className="text-[#00d4aa]" />
          </div>
          {sidebarOpen && (
            <div className="min-w-0">
              <div className="text-[#e8eaf0] font-semibold text-xs leading-tight truncate">PowerPrice</div>
              <div className="text-[#8892b0] text-[10px] truncate">CFD Signals · DE</div>
            </div>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="ml-auto text-[#4a5568] hover:text-[#8892b0] transition-colors flex-shrink-0"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
              {sidebarOpen
                ? <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
                : <path d="M5 2l5 5-5 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
              }
            </svg>
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 overflow-y-auto scrollbar-thin">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-4 py-2.5 text-xs transition-all duration-150 group relative',
                  isActive
                    ? 'text-[#00d4aa] bg-[#00d4aa]/5 border-r-2 border-[#00d4aa]'
                    : 'text-[#8892b0] hover:text-[#e8eaf0] hover:bg-[#141b2d]'
                )
              }
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {sidebarOpen && <span className="truncate">{item.label}</span>}
              {!sidebarOpen && (
                <div className="absolute left-full ml-2 px-2 py-1 bg-[#141b2d] border border-[#1e2d4a] rounded text-xs text-[#e8eaf0] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                  {item.label}
                </div>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Connection status */}
        <div className="px-4 py-3 border-t border-[#1e2d4a]">
          <div className={clsx('flex items-center gap-2 text-[10px]', sidebarOpen ? '' : 'justify-center')}>
            {connected === null ? (
              <div className="w-2 h-2 rounded-full bg-[#ffa726] animate-pulse flex-shrink-0" />
            ) : connected ? (
              <Wifi size={12} className="text-[#00d4aa] flex-shrink-0" />
            ) : (
              <WifiOff size={12} className="text-[#ff4757] flex-shrink-0" />
            )}
            {sidebarOpen && (
              <span className={connected ? 'text-[#00d4aa]' : connected === null ? 'text-[#ffa726]' : 'text-[#ff4757]'}>
                {connected === null ? 'Connecting…' : connected ? 'API Online' : 'API Offline'}
              </span>
            )}
          </div>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Disclaimer banner */}
        <div className="flex-shrink-0 flex items-center gap-2 px-4 py-1.5 bg-[#ffa726]/10 border-b border-[#ffa726]/30">
          <AlertTriangle size={13} className="text-[#ffa726] flex-shrink-0" />
          <span className="text-[10px] text-[#ffa726] font-medium">
            SIGNAL ONLY — Not financial advice. CFD trading involves substantial risk of loss. For informational purposes only.
          </span>
        </div>

        {/* Header */}
        <header className="flex-shrink-0 flex items-center justify-between px-5 py-2.5 border-b border-[#1e2d4a] bg-[#0f1629]">
          <div className="flex items-center gap-3">
            <span className="text-[#4a5568] text-xs">German Electricity Market</span>
            <span className="text-[#1e2d4a]">|</span>
            <span className="text-[#8892b0] text-xs">EPEX SPOT · Day-Ahead</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-[#8892b0] text-xs font-mono">
              {format(now, 'yyyy-MM-dd')}
            </div>
            <div className="text-[#00d4aa] text-xs font-mono font-semibold tabular-nums">
              {format(now, 'HH:mm:ss')} CET
            </div>
            <div
              className={clsx(
                'flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium border',
                connected
                  ? 'text-[#00d4aa] bg-[#00d4aa]/5 border-[#00d4aa]/30'
                  : 'text-[#ff4757] bg-[#ff4757]/5 border-[#ff4757]/30'
              )}
            >
              <span
                className={clsx(
                  'w-1.5 h-1.5 rounded-full',
                  connected ? 'bg-[#00d4aa] animate-pulse' : 'bg-[#ff4757]'
                )}
              />
              {connected ? 'LIVE' : 'OFFLINE'}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto scrollbar-thin p-5">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
