export type Measurement = {
  id: number
  ts: number
  co2: number
  temperature: number
  humidity: number
}

export type AppConfig = {
  ntfy_topic: string | null
}
