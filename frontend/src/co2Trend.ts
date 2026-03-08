import type { Measurement } from './types'

export const CO2_TREND_RECENT_WINDOW_SECONDS = 2 * 60
export const CO2_TREND_BASELINE_OFFSET_SECONDS = 10 * 60
export const CO2_TREND_BASELINE_WINDOW_SECONDS = 2 * 60
export const CO2_TREND_NEUTRAL_PERCENT_THRESHOLD = 1

export type Co2TrendDirection = 'rising' | 'falling' | 'neutral'

export type Co2Trend = {
  direction: Co2TrendDirection
  percentage: number
  rawPercentage: number
  recentAverage: number
  baselineAverage: number
  referenceTs: number
}

function getAverageCo2InWindow(measurements: Measurement[], startTs: number, endTs: number): number | null {
  const values = measurements.filter((item) => item.ts >= startTs && item.ts <= endTs).map((item) => item.co2)
  if (values.length === 0) return null

  const total = values.reduce((sum, value) => sum + value, 0)
  return total / values.length
}

function getTrendDirection(percentage: number): Co2TrendDirection {
  if (percentage >= CO2_TREND_NEUTRAL_PERCENT_THRESHOLD) return 'rising'
  if (percentage <= -CO2_TREND_NEUTRAL_PERCENT_THRESHOLD) return 'falling'
  return 'neutral'
}

export function calculateCo2Trend(measurements: Measurement[]): Co2Trend | null {
  if (measurements.length === 0) return null

  const referenceTs = measurements[measurements.length - 1]?.ts
  if (referenceTs === undefined) return null

  const recentStart = referenceTs - CO2_TREND_RECENT_WINDOW_SECONDS
  const baselineEnd = referenceTs - CO2_TREND_BASELINE_OFFSET_SECONDS
  const baselineStart = baselineEnd - CO2_TREND_BASELINE_WINDOW_SECONDS

  const recentAverage = getAverageCo2InWindow(measurements, recentStart, referenceTs)
  const baselineAverage = getAverageCo2InWindow(measurements, baselineStart, baselineEnd)

  if (recentAverage === null || baselineAverage === null || baselineAverage <= 0) return null

  const rawPercentage = ((recentAverage - baselineAverage) / baselineAverage) * 100
  const direction = getTrendDirection(rawPercentage)
  const percentage = direction === 'neutral' ? 0 : rawPercentage

  return {
    direction,
    percentage,
    rawPercentage,
    recentAverage,
    baselineAverage,
    referenceTs,
  }
}

export function formatCo2TrendPercentage(percentage: number): string {
  if (percentage === 0) return '0.0%'
  return `${percentage > 0 ? '+' : ''}${percentage.toFixed(1)}%`
}
