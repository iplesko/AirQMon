export type Measurement = {
  id: number
  ts: number
  co2: number
  temperature: number
  humidity: number
}

export type AppConfig = {
  ntfy_topic: string | null
  co2_high: number
  co2_clear: number
  cooldown_seconds: number
}
