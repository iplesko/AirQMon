import { calculateCo2Trend, formatCo2TrendPercentage } from './co2Trend'
import type { Measurement } from './types'

type Co2Quality = 'amazing' | 'good' | 'average' | 'bad' | 'awful'

function getCo2Quality(value: number | undefined): Co2Quality | '' {
  if (value === undefined || value === null) return ''
  if (value <= 600) return 'amazing'
  if (value <= 1000) return 'good'
  if (value <= 1500) return 'average'
  if (value < 2000) return 'bad'
  return 'awful'
}

function co2ColorClass(value: number | undefined) {
  const quality = getCo2Quality(value)
  return quality ? `co2-${quality}` : ''
}

function formatReading(value: number, unit: string, decimals: number): string {
  if (value === undefined || value === null) return '--'
  return `${value.toFixed(decimals)} ${unit}`
}

function getTrendArrow(direction: 'rising' | 'falling' | 'neutral'): string {
  if (direction === 'rising') return '\u2197'
  if (direction === 'falling') return '\u2198'
  return '\u2192'
}

function buildTrendMeasurements(data: Measurement[], latest: Measurement | null): Measurement[] {
  if (!latest) return data
  if (data.some((item) => item.ts === latest.ts)) return data
  return [...data, latest].sort((a, b) => a.ts - b.ts)
}

export default function CurrentReading({ latest, data }: { latest: Measurement | null; data: Measurement[] }) {
  const trend = calculateCo2Trend(buildTrendMeasurements(data, latest))

  return (
    <div className="card latest">
      <div className="muted">Latest measurement</div>
      <div className="latest-grid">
        <div className="latest-column latest-column-primary">
          <div className="latest-reading-group">
            <div className={`co2-big co2-value ${latest ? co2ColorClass(latest.co2) : ''}`}>
              {latest ? `${latest.co2} ppm` : '--'}
            </div>
            <div className="trend-block">
              <div className="trend-label">10 min trend</div>
              <div className={`trend-indicator ${trend ? `trend-${trend.direction}` : 'trend-neutral'}`}>
                <span className="trend-arrow" aria-hidden="true">
                  {trend ? getTrendArrow(trend.direction) : '\u2192'}
                </span>
                <span>{trend ? formatCo2TrendPercentage(trend.percentage) : '--'}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="latest-column latest-column-details">
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
