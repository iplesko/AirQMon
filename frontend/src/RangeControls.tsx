type RangeControlsProps = {
  rangeSeconds: number
  onSelectRange: (value: number) => void
}

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

export default function RangeControls({ rangeSeconds, onSelectRange }: RangeControlsProps) {
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
