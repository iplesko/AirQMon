import { useEffect } from 'react'

type RangeControlsProps = {
  rangeSeconds: number
  onSelectRange: (value: number) => void
}

const RANGE_SECONDS_STORAGE_KEY = 'airqmon.rangeSeconds'
const RANGE_OPTIONS = [
  { label: '7d', value: 7 * 24 * 3600 },
  { label: '24h', value: 24 * 3600 },
  { label: '12h', value: 12 * 3600 },
  { label: '8h', value: 8 * 3600 },
  { label: '6h', value: 6 * 3600 },
  { label: '4h', value: 4 * 3600 },
  { label: '2h', value: 2 * 3600 },
  { label: '1h', value: 3600 },
  { label: '30m', value: 30 * 60 },
]
const DEFAULT_RANGE_SECONDS = 24 * 3600

function isRangeOption(value: number): boolean {
  return RANGE_OPTIONS.some((option) => option.value === value)
}

export function getInitialRangeSeconds(): number {
  if (typeof window === 'undefined') return DEFAULT_RANGE_SECONDS

  try {
    const stored = window.localStorage.getItem(RANGE_SECONDS_STORAGE_KEY)
    if (!stored) return DEFAULT_RANGE_SECONDS

    const parsed = Number(stored)
    if (!Number.isInteger(parsed) || !isRangeOption(parsed)) return DEFAULT_RANGE_SECONDS
    return parsed
  } catch {
    return DEFAULT_RANGE_SECONDS
  }
}

function persistRangeSeconds(rangeSeconds: number): void {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.setItem(RANGE_SECONDS_STORAGE_KEY, String(rangeSeconds))
  } catch {
    // Ignore storage failures (private mode, blocked storage, etc).
  }
}

export default function RangeControls({ rangeSeconds, onSelectRange }: RangeControlsProps) {
  useEffect(() => {
    persistRangeSeconds(rangeSeconds)
  }, [rangeSeconds])

  return (
    <div className="range-controls">
      <span className="muted range-label">Range</span>
      <div className="range-scroll" role="group" aria-label="Select history range">
        {RANGE_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`range-chip ${rangeSeconds === option.value ? 'active' : ''}`}
            onClick={() => onSelectRange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}
