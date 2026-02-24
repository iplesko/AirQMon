import { useEffect, useState } from 'react'
import type { AppConfig } from '../types'
import NotificationsControl from './NotificationsControl'
import './ConfigModal.css'

type ConfigModalProps = {
  open: boolean
  onClose: () => void
}

type ConfigForm = {
  co2_high: string
  co2_clear: string
  cooldown_seconds: string
}

function configToForm(config: AppConfig): ConfigForm {
  return {
    co2_high: String(config.co2_high),
    co2_clear: String(config.co2_clear),
    cooldown_seconds: String(config.cooldown_seconds),
  }
}

async function getApiErrorMessage(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null
  return payload?.detail ?? `Request failed (${response.status})`
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export default function ConfigModal({ open, onClose }: ConfigModalProps) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [saveStatus, setSaveStatus] = useState<string | null>(null)
  const [form, setForm] = useState<ConfigForm>({
    co2_high: '',
    co2_clear: '',
    cooldown_seconds: '',
  })

  useEffect(() => {
    if (!open) return

    let canceled = false

    const loadConfig = async () => {
      setLoading(true)
      setErrorMessage(null)
      setSaveStatus(null)
      try {
        const res = await fetch('/api/config')
        if (!res.ok) {
          throw new Error(await getApiErrorMessage(res))
        }
        const payload = (await res.json()) as AppConfig
        if (!canceled) {
          setForm(configToForm(payload))
        }
      } catch (error) {
        if (!canceled) {
          setErrorMessage(`Failed to load config: ${getErrorMessage(error, 'Unknown error')}`)
        }
      } finally {
        if (!canceled) {
          setLoading(false)
        }
      }
    }

    void loadConfig()

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

  const handleSave = async () => {
    const co2High = Number(form.co2_high)
    const co2Clear = Number(form.co2_clear)
    const cooldownSeconds = Number(form.cooldown_seconds)

    if (!Number.isFinite(co2High) || !Number.isFinite(co2Clear) || !Number.isFinite(cooldownSeconds)) {
      setErrorMessage('Config values must be numeric')
      return
    }
    if (!Number.isInteger(co2High) || !Number.isInteger(co2Clear)) {
      setErrorMessage('CO2 high and CO2 clear must be integers')
      return
    }
    if (!Number.isInteger(cooldownSeconds) || cooldownSeconds < 0) {
      setErrorMessage('Cooldown must be a non-negative integer')
      return
    }
    if (co2Clear >= co2High) {
      setErrorMessage('CO2 clear must be lower than CO2 high')
      return
    }

    setSaving(true)
    setErrorMessage(null)
    setSaveStatus(null)
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          co2_high: co2High,
          co2_clear: co2Clear,
          cooldown_seconds: cooldownSeconds,
        }),
      })
      if (!res.ok) {
        throw new Error(await getApiErrorMessage(res))
      }
      const updated = (await res.json()) as AppConfig
      setForm(configToForm(updated))
      setSaveStatus('Saved')
    } catch (error) {
      setErrorMessage(`Failed to save config: ${getErrorMessage(error, 'Unknown error')}`)
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = () => {
    window.location.assign('/cdn-cgi/access/logout')
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
        {errorMessage ? <div className="modal-error">{errorMessage}</div> : null}

        {!loading ? (
          <div className="modal-content">
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

            <NotificationsControl />

            <div className="config-actions">
              <button className="btn danger" onClick={handleLogout}>
                Log out
              </button>
              <div className="config-actions-right">
                {saveStatus ? <div className="config-copy-status">{saveStatus}</div> : null}
                <button className="btn" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
