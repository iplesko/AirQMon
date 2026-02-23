import { useCallback, useEffect, useRef, useState } from 'react'
import Brand from './Brand'
import CurrentReading from './CurrentReading'
import MeasurementChart from './MeasurementChart'
import RangeControls from './RangeControls'
import ThemeToggle, { getInitialDarkMode } from './ThemeToggle'
import type { Measurement } from './types'

const DEFAULT_RANGE_SECONDS = 24 * 3600
const POLL_INTERVAL_MS = 5000
const MOBILE_BREAKPOINT = 768
const MOBILE_PORTRAIT_POINTS = 100

function isMobilePortraitViewport(): boolean {
  if (typeof window === 'undefined') return false
  return window.innerWidth <= MOBILE_BREAKPOINT && window.innerHeight > window.innerWidth
}

function getInitialUseLimitedPoints(): boolean {
  return isMobilePortraitViewport()
}

function mergeAndWindowData(existing: Measurement[], incoming: Measurement[], windowStart: number): Measurement[] {
  const merged = [...existing, ...incoming]
  const seen = new Set<number>()
  const deduped: Measurement[] = []

  for (const item of merged) {
    if (!seen.has(item.ts)) {
      seen.add(item.ts)
      deduped.push(item)
    }
  }

  deduped.sort((a, b) => a.ts - b.ts)
  return deduped.filter((item) => item.ts >= windowStart)
}

function getNextLastFetchTs(incoming: Measurement[], previousTs: number | null, windowStart: number): number {
  const maxIncomingTs = incoming.length > 0 ? Math.max(...incoming.map((item) => item.ts)) : 0
  return Math.max(previousTs ?? 0, maxIncomingTs, windowStart)
}

export default function App() {
  const [data, setData] = useState<Measurement[]>([])
  const [latest, setLatest] = useState<Measurement | null>(null)
  const [dark, setDark] = useState<boolean>(getInitialDarkMode)
  const [rangeSeconds, setRangeSeconds] = useState<number>(DEFAULT_RANGE_SECONDS)
  const [useLimitedPoints, setUseLimitedPoints] = useState<boolean>(getInitialUseLimitedPoints)
  const lastFetchTsRef = useRef<number | null>(null)

  const fetchLatest = useCallback(async () => {
    try {
      const res = await fetch('/api/latest')
      if (!res.ok) {
        setLatest(null)
        return
      }
      const payload = await res.json()
      setLatest(payload)
    } catch (e) {
      console.error('fetchLatest', e)
      setLatest(null)
    }
  }, [])

  const fetchRange = useCallback(
    async (forceFull = false) => {
      try {
        const end = Math.floor(Date.now() / 1000)
        const windowStart = end - rangeSeconds
        const shouldForceFull = forceFull || useLimitedPoints
        const previousTs = lastFetchTsRef.current
        const start = shouldForceFull || previousTs === null ? windowStart : Math.max(previousTs + 1, windowStart)
        const query = new URLSearchParams({ start: String(start), end: String(end) })
        if (useLimitedPoints) {
          query.set('points', String(MOBILE_PORTRAIT_POINTS))
        }

        const res = await fetch(`/api/data?${query.toString()}`)
        if (!res.ok) return

        const payload = await res.json()
        if (!payload || !Array.isArray(payload.data)) return

        const incoming = payload.data as Measurement[]

        if (shouldForceFull) {
          setData(incoming)
        } else {
          setData((prev) => mergeAndWindowData(prev, incoming, windowStart))
        }

        const nextTs = getNextLastFetchTs(incoming, previousTs, windowStart)
        lastFetchTsRef.current = nextTs
      } catch (e) {
        console.error('fetchRange', e)
      }
    },
    [rangeSeconds, useLimitedPoints]
  )

  // Full reload for initial mount and each selected range change.
  useEffect(() => {
    lastFetchTsRef.current = null
    void fetchRange(true)
    void fetchLatest()
  }, [rangeSeconds, fetchLatest, fetchRange])

  // Poll latest snapshot and range delta every 5s.
  useEffect(() => {
    const id = setInterval(() => {
      void fetchLatest()
      void fetchRange(false)
    }, POLL_INTERVAL_MS)

    return () => clearInterval(id)
  }, [fetchLatest, fetchRange])

  // Enable point-limited queries only on mobile portrait.
  useEffect(() => {
    const updateViewportMode = () => {
      setUseLimitedPoints(isMobilePortraitViewport())
    }

    updateViewportMode()
    window.addEventListener('resize', updateViewportMode)
    window.addEventListener('orientationchange', updateViewportMode)
    return () => {
      window.removeEventListener('resize', updateViewportMode)
      window.removeEventListener('orientationchange', updateViewportMode)
    }
  }, [])

  return (
    <div className="app">
      <div className="header">
        <Brand />
        <div className="controls">
          <RangeControls rangeSeconds={rangeSeconds} onSelectRange={setRangeSeconds} />
          <ThemeToggle dark={dark} onToggle={() => setDark((value) => !value)} />
        </div>
      </div>

      <div className="grid">
        <CurrentReading latest={latest} />
        <div className="card chartWrap">
          <MeasurementChart data={data} dark={dark} />
        </div>
      </div>
    </div>
  )
}
