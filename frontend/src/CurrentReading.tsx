import type { Measurement } from './types'

function co2ColorClass(value: number | undefined) {
  if (value === undefined || value === null) return ''
  if (value >= 2000) return 'co2-very-high'
  if (value >= 1000) return 'co2-high'
  return ''
}

function formatReading(value: number, unit: string, decimals: number): string {
  if (value === undefined || value === null) return '--'
  return `${value.toFixed(decimals)} ${unit}`
}

export default function CurrentReading({ latest }: { latest: Measurement | null }) {
  return (
    <div className="card latest">
      <div className="muted">Latest measurement</div>
      <div className="latest-row">
        <div className={`co2-big co2-value ${latest ? co2ColorClass(latest.co2) : ''}`}>
          {latest ? `${latest.co2} ppm` : '--'}
        </div>
        <div className="latest-right">
          <div className="timestamp">{latest ? `${new Date(latest.ts * 1000).toLocaleString()}` : ''}</div>
          <div className="latest-meta">
            <div className="stat">
              <div className="label">Temperature</div>
              <div className="value">{latest ? formatReading(latest.temperature, '\u00B0C', 2) : '--'}</div>
            </div>
            <div className="stat">
              <div className="label">Humidity</div>
              <div className="value">{latest ? formatReading(latest.humidity, '%', 2) : '--'}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
