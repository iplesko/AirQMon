import { useEffect, useState } from 'react'
import type { AppConfig } from '../types'
import './ConfigModal.css'

type ConfigModalProps = {
  open: boolean
  onClose: () => void
}

type ConfigForm = Record<keyof AppConfig, string>

function configToForm(config: AppConfig): ConfigForm {
  return {
    ntfy_topic: config.ntfy_topic ?? '',
    co2_high: String(config.co2_high),
    co2_clear: String(config.co2_clear),
    cooldown_seconds: String(config.cooldown_seconds),
  }
}

export default function ConfigModal({ open, onClose }: ConfigModalProps) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveStatus, setSaveStatus] = useState<string | null>(null)
  const [copyStatus, setCopyStatus] = useState<string | null>(null)
  const [form, setForm] = useState<ConfigForm>({
    ntfy_topic: '',
    co2_high: '',
    co2_clear: '',
    cooldown_seconds: '',
  })

  useEffect(() => {
    if (!open) return

    let canceled = false

    const fetchConfig = async () => {
      setLoading(true)
      setError(null)
      setSaveStatus(null)
      setCopyStatus(null)
      try {
        const res = await fetch('/api/config')
        if (!res.ok) {
          throw new Error(`Request failed (${res.status})`)
        }
        const payload = (await res.json()) as AppConfig
        if (!canceled) {
          setForm(configToForm(payload))
        }
      } catch (e) {
        if (!canceled) {
          setError(e instanceof Error ? e.message : 'Failed to load config')
        }
      } finally {
        if (!canceled) {
          setLoading(false)
        }
      }
    }

    void fetchConfig()

    return () => {
      canceled = true
    }
  }, [open])

  useEffect(() => {
    if (!open) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  const topic = form.ntfy_topic.trim()

  const handleCopy = async () => {
    if (!topic) return
    try {
      await navigator.clipboard.writeText(topic)
      setCopyStatus('Copied')
    } catch {
      setCopyStatus('Copy failed')
    }
  }

  const handleSave = async () => {
    const ntfyTopic = form.ntfy_topic.trim()
    const co2High = Number(form.co2_high)
    const co2Clear = Number(form.co2_clear)
    const cooldownSeconds = Number(form.cooldown_seconds)

    if (!ntfyTopic) {
      setError('Topic must not be empty')
      return
    }
    if (!Number.isFinite(co2High) || !Number.isFinite(co2Clear) || !Number.isFinite(cooldownSeconds)) {
      setError('Config values must be numeric')
      return
    }
    if (!Number.isInteger(co2High) || !Number.isInteger(co2Clear)) {
      setError('CO2 high and CO2 clear must be integers')
      return
    }
    if (!Number.isInteger(cooldownSeconds) || cooldownSeconds < 0) {
      setError('Cooldown must be a non-negative integer')
      return
    }
    if (co2Clear >= co2High) {
      setError('CO2 clear must be lower than CO2 high')
      return
    }

    setSaving(true)
    setError(null)
    setSaveStatus(null)
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ntfy_topic: ntfyTopic,
          co2_high: co2High,
          co2_clear: co2Clear,
          cooldown_seconds: cooldownSeconds,
        }),
      })
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as { detail?: string } | null
        throw new Error(payload?.detail ?? `Request failed (${res.status})`)
      }
      const updated = (await res.json()) as AppConfig
      setForm(configToForm(updated))
      setSaveStatus('Saved')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save config')
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return null
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-label="Configuration" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Configuration</h2>
          <button className="btn secondary" onClick={onClose}>
            Close
          </button>
        </div>

        {loading ? <div className="muted">Loading config...</div> : null}
        {error ? <div className="modal-error">Failed to load config: {error}</div> : null}

        {!loading ? (
          <div className="modal-content">
            <div className="config-row">
              <label className="config-label" htmlFor="config-ntfy-topic">
                ntfy topic
              </label>
              <div className="config-value-wrap">
                <input
                  id="config-ntfy-topic"
                  className="config-input config-input-topic"
                  value={form.ntfy_topic}
                  onChange={(event) => setForm((prev) => ({ ...prev, ntfy_topic: event.target.value }))}
                />
                <button className="btn secondary" onClick={handleCopy} disabled={!topic}>
                  Copy
                </button>
              </div>
              <div className="config-help">ℹ️ Topic name used by <a href="https://ntfy.sh" target="_blank" rel="noopener noreferrer">ntfy.sh</a> for publishing and subscribing to alerts.</div>
            </div>
            {copyStatus ? <div className="config-copy-status">{copyStatus}</div> : null}

            <div className="config-row">
              <label className="config-label" htmlFor="config-co2-high">
                CO2 high (ppm)
              </label>
              <input
                id="config-co2-high"
                className="config-input"
                type="number"
                step="1"
                value={form.co2_high}
                onChange={(event) => setForm((prev) => ({ ...prev, co2_high: event.target.value }))}
              />
              <div className="config-help">ℹ️ High threshold that triggers an alert when CO2 reaches or exceeds this value.</div>
            </div>

            <div className="config-row">
              <label className="config-label" htmlFor="config-co2-clear">
                CO2 clear (ppm)
              </label>
              <input
                id="config-co2-clear"
                className="config-input"
                type="number"
                step="1"
                value={form.co2_clear}
                onChange={(event) => setForm((prev) => ({ ...prev, co2_clear: event.target.value }))}
              />
              <div className="config-help">ℹ️ Recovery threshold that clears alert state when CO2 drops to or below this value.</div>
            </div>

            <div className="config-row">
              <label className="config-label" htmlFor="config-cooldown-seconds">
                Cooldown seconds
              </label>
              <input
                id="config-cooldown-seconds"
                className="config-input"
                type="number"
                step="1"
                min="0"
                value={form.cooldown_seconds}
                onChange={(event) => setForm((prev) => ({ ...prev, cooldown_seconds: event.target.value }))}
              />
              <div className="config-help">ℹ️ Minimum seconds between starting one high alert and allowing the next one.</div>
            </div>

            <div className="config-actions">
              <button className="btn" onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save'}
              </button>
              {saveStatus ? <div className="config-copy-status">{saveStatus}</div> : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

