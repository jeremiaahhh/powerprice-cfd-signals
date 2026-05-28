import { useState, useEffect, useCallback, useRef } from 'react'
import { Signal, getSignal, getSignalHistory } from '../api/client'

interface UseSignalOptions {
  autoRefresh?: boolean
  intervalMs?: number
  includeHistory?: boolean
  historyLimit?: number
}

interface UseSignalReturn {
  signal: Signal | null
  history: Signal[]
  loading: boolean
  error: string | null
  lastRefresh: Date | null
  refresh: () => Promise<void>
}

// Mock signal data for when the API is offline
function mockSignal(): Signal {
  const now = new Date().toISOString()
  const currentPrice = -(Math.random() * 30 + 5) // Negative price scenario
  return {
    id: `mock-${Date.now()}`,
    timestamp: now,
    action: 'WATCH',
    confidence: 0.72,
    confidence_breakdown: {
      ml_model: 0.78,
      price_level: 0.81,
      momentum: 0.65,
      volume_signal: 0.59,
      weather_factor: 0.74,
      overall: 0.72
    },
    current_price: currentPrice,
    predicted_price: Math.abs(currentPrice) * 0.6,
    p_negative: 0.83,
    p_rebound: 0.71,
    net_edge: 12.40,
    stop_loss: currentPrice - 5,
    take_profit: currentPrice + 25,
    reason: 'High solar generation + low demand. Negative price spike expected. Rebound probability elevated. [DEMO DATA]',
    risk_warnings: [
      'API offline — displaying demo data',
      'Negative price event likely within 2h window',
      'Liquidity may be limited at these levels'
    ],
    cost_breakdown: {
      spread: 1.2,
      slippage: 0.8,
      financing: 0.15,
      broker_markup: 0.5,
      safety_buffer: 2.0,
      total: 4.65,
      net_edge: 12.40
    },
    horizon_hours: 6
  }
}

export default function useSignal({
  autoRefresh = true,
  intervalMs = 30000,
  includeHistory = false,
  historyLimit = 20
}: UseSignalOptions = {}): UseSignalReturn {
  const [signal, setSignal] = useState<Signal | null>(null)
  const [history, setHistory] = useState<Signal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const refresh = useCallback(async () => {
    if (!mountedRef.current) return
    setLoading(true)
    setError(null)

    try {
      const [signalData, historyData] = await Promise.all([
        getSignal(),
        includeHistory ? getSignalHistory(historyLimit) : Promise.resolve([])
      ])

      if (mountedRef.current) {
        setSignal(signalData)
        if (includeHistory) setHistory(historyData)
        setLastRefresh(new Date())
        setError(null)
      }
    } catch (err) {
      if (mountedRef.current) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to fetch signal'
        setError(errorMsg)
        // Use mock data when API is unavailable
        if (!signal) {
          setSignal(mockSignal())
          setLastRefresh(new Date())
        }
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false)
      }
    }
  }, [includeHistory, historyLimit, signal])

  // Initial fetch
  useEffect(() => {
    refresh()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refresh interval
  useEffect(() => {
    if (!autoRefresh) return
    const timer = setInterval(refresh, intervalMs)
    return () => clearInterval(timer)
  }, [autoRefresh, intervalMs, refresh])

  return { signal, history, loading, error, lastRefresh, refresh }
}
