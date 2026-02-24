import { useEffect, useState } from 'react'
import type { AppConfig } from '../types'
import './ConfigModal.css'

type ConfigModalProps = {
  open: boolean
  onClose: () => void
}

export default function ConfigModal({ open, onClose }: ConfigModalProps) {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copyStatus, setCopyStatus] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return

    let canceled = false

    const fetchConfig = async () => {
      setLoading(true)
      setError(null)
      setCopyStatus(null)
      try {
        const res = await fetch('/api/config')
        if (!res.ok) {
          throw new Error(`Request failed (${res.status})`)
        }
        const payload = (await res.json()) as AppConfig
        if (!canceled) {
          setConfig(payload)
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

  const topic = config?.ntfy_topic ?? null

  const handleCopy = async () => {
    if (!topic) return
    try {
      await navigator.clipboard.writeText(topic)
      setCopyStatus('Copied')
    } catch {
      setCopyStatus('Copy failed')
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

        {!loading && !error ? (
          <div className="modal-content">
            <div className="config-row">
              <div className="config-label">ntfy topic</div>
              <div className="config-value-wrap">
                <div className="config-value">{topic ?? 'Not set yet (start alerter to generate one)'}</div>
                <button className="btn secondary" onClick={handleCopy} disabled={!topic}>
                  Copy
                </button>
              </div>
            </div>
            <div className="config-help">
              Use this topic with ntfy clients to subscribe or publish alerts.
            </div>
            {copyStatus ? <div className="config-copy-status">{copyStatus}</div> : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
