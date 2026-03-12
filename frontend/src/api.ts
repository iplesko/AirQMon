import type { AppConfig, Measurement } from './types'

type MeasurementRangeParams = {
  start: number
  end: number
  points?: number
}

type MeasurementRangeResponse = {
  data?: Measurement[]
}

type ConfigUpdatePayload = {
  co2_high: number
  co2_clear: number
  cooldown_seconds: number
  display_brightness: number
  night_mode_enabled: boolean
}

type PushPublicKeyResponse = {
  public_key?: string
}

type PushSubscriptionResponse = {
  ok: boolean
}

type PushUnsubscribeResponse = {
  ok: boolean
  deleted: boolean
}

async function getApiErrorMessage(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null
  return payload?.detail ?? `Request failed (${response.status})`
}

export function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    throw new Error(await getApiErrorMessage(response))
  }
  return (await response.json()) as T
}

export async function fetchLatestMeasurement(): Promise<Measurement | null> {
  const response = await fetch('/api/latest')
  if (!response.ok) {
    return null
  }
  return (await response.json()) as Measurement
}

export async function fetchMeasurementRange(params: MeasurementRangeParams): Promise<Measurement[] | null> {
  const query = new URLSearchParams({
    start: String(params.start),
    end: String(params.end),
  })
  if (params.points !== undefined) {
    query.set('points', String(params.points))
  }

  const response = await fetch(`/api/data?${query.toString()}`)
  if (!response.ok) {
    return null
  }

  const payload = (await response.json()) as MeasurementRangeResponse | null
  if (!payload || !Array.isArray(payload.data)) {
    return null
  }

  return payload.data
}

export async function fetchConfig(): Promise<AppConfig> {
  return requestJson<AppConfig>('/api/config')
}

export async function updateConfig(payload: ConfigUpdatePayload): Promise<AppConfig> {
  return requestJson<AppConfig>('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function fetchPushPublicKey(): Promise<string> {
  const payload = await requestJson<PushPublicKeyResponse>('/api/push/public-key')
  const publicKey = (payload.public_key ?? '').trim()
  if (!publicKey) {
    throw new Error('Server did not return a VAPID public key')
  }
  return publicKey
}

export async function subscribePushSubscription(subscription: PushSubscription): Promise<void> {
  await requestJson<PushSubscriptionResponse>('/api/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subscription),
  })
}

export async function unsubscribePushSubscription(endpoint: string): Promise<boolean> {
  const payload = await requestJson<PushUnsubscribeResponse>('/api/push/unsubscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint }),
  })
  return payload.deleted
}
