import { useEffect, useState } from 'react'
import { registerAirqmonServiceWorker } from '../serviceWorker'

type NotificationMode = 'enabled' | 'disabled' | 'unsupported'
type NotificationAction = 'enable' | 'disable' | null
type StatusTone = 'success' | 'danger' | 'info'

type InlineStatus = {
  message: string
  tone: StatusTone
}

function urlBase64ToUint8Array(base64Url: string): Uint8Array {
  const padding = '='.repeat((4 - (base64Url.length % 4)) % 4)
  const base64 = (base64Url + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  return Uint8Array.from(rawData, (char) => char.charCodeAt(0))
}

function getNotificationsSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  )
}

async function getApiErrorMessage(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null
  return payload?.detail ?? `Request failed (${response.status})`
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function getStatusClassName(status: InlineStatus): string {
  if (status.tone === 'danger') {
    return 'config-copy-status config-copy-status-danger'
  }
  if (status.tone === 'info') {
    return 'config-copy-status config-copy-status-info'
  }
  return 'config-copy-status'
}

export default function NotificationsControl() {
  const [notificationAction, setNotificationAction] = useState<NotificationAction>(null)
  const [notificationMode, setNotificationMode] = useState<NotificationMode>('disabled')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [notificationStatus, setNotificationStatus] = useState<InlineStatus | null>(null)

  const notificationsSupported = getNotificationsSupported()
  const notificationsBusy = notificationAction !== null

  useEffect(() => {
    let canceled = false

    const refreshNotificationMode = async () => {
      setNotificationStatus(null)
      setErrorMessage(null)

      if (!notificationsSupported) {
        if (!canceled) {
          setNotificationMode('unsupported')
        }
        return
      }

      try {
        const registration = await navigator.serviceWorker.getRegistration()
        const subscription = registration ? await registration.pushManager.getSubscription() : null
        if (canceled) return

        if (subscription) {
          setNotificationMode('enabled')
          setNotificationStatus({ message: 'Notifications enabled', tone: 'success' })
        } else {
          setNotificationMode('disabled')
        }
      } catch {
        if (!canceled) {
          setNotificationMode('disabled')
        }
      }
    }

    void refreshNotificationMode()

    return () => {
      canceled = true
    }
  }, [notificationsSupported])

  const handleEnableNotifications = async () => {
    setErrorMessage(null)
    setNotificationStatus(null)

    if (!notificationsSupported) {
      setErrorMessage('Notifications are not supported in this browser/context. Use HTTPS (or localhost) and a modern browser.')
      return
    }
    if (Notification.permission === 'denied') {
      setErrorMessage('Notifications are blocked in browser settings for this site.')
      return
    }

    setNotificationAction('enable')
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        setErrorMessage('Notification permission was not granted.')
        return
      }

      const registration = await registerAirqmonServiceWorker()

      const keyResponse = await fetch('/api/push/public-key')
      if (!keyResponse.ok) {
        throw new Error(await getApiErrorMessage(keyResponse))
      }
      const keyPayload = (await keyResponse.json()) as { public_key?: string }
      const publicKey = (keyPayload.public_key ?? '').trim()
      if (!publicKey) {
        throw new Error('Server did not return a VAPID public key')
      }

      let subscription = await registration.pushManager.getSubscription()
      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
        })
      }

      const subscribeResponse = await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription),
      })
      if (!subscribeResponse.ok) {
        throw new Error(await getApiErrorMessage(subscribeResponse))
      }

      setNotificationMode('enabled')
      setNotificationStatus({ message: 'Notifications enabled', tone: 'success' })
    } catch (error) {
      setErrorMessage(`Failed to enable notifications: ${getErrorMessage(error, 'Unknown error')}`)
    } finally {
      setNotificationAction(null)
    }
  }

  const handleDisableNotifications = async () => {
    setErrorMessage(null)
    setNotificationStatus(null)

    if (!notificationsSupported) {
      setErrorMessage('Notifications are not supported in this browser/context.')
      return
    }

    setNotificationAction('disable')
    try {
      const registration = await navigator.serviceWorker.getRegistration()
      const subscription = registration ? await registration.pushManager.getSubscription() : null
      if (!subscription) {
        setNotificationMode('disabled')
        setNotificationStatus({ message: 'Notifications already disabled', tone: 'info' })
        return
      }

      await subscription.unsubscribe()

      const unsubscribeResponse = await fetch('/api/push/unsubscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      })

      setNotificationMode('disabled')
      if (unsubscribeResponse.ok) {
        setNotificationStatus({ message: 'Notifications disabled', tone: 'danger' })
      } else {
        setNotificationStatus({ message: 'Disabled in browser, but backend cleanup failed', tone: 'info' })
      }
    } catch (error) {
      setErrorMessage(`Failed to disable notifications: ${getErrorMessage(error, 'Unknown error')}`)
    } finally {
      setNotificationAction(null)
    }
  }

  return (
    <div className="config-row">
      <label className="config-label">Notifications</label>
      <div className="config-value-wrap">
        {notificationMode === 'disabled' ? (
          <button className="btn" onClick={handleEnableNotifications} disabled={notificationsBusy}>
            {notificationAction === 'enable' ? 'Enabling...' : 'Enable notifications'}
          </button>
        ) : null}
        {notificationMode === 'enabled' ? (
          <button className="btn secondary" onClick={handleDisableNotifications} disabled={notificationsBusy}>
            {notificationAction === 'disable' ? 'Disabling...' : 'Disable notifications'}
          </button>
        ) : null}
        {notificationMode === 'unsupported' ? (
          <div className="config-copy-status config-copy-status-info">Notifications unsupported in this context</div>
        ) : null}
        {notificationStatus ? <div className={getStatusClassName(notificationStatus)}>{notificationStatus.message}</div> : null}
      </div>
      {errorMessage ? <div className="modal-error">{errorMessage}</div> : null}
    </div>
  )
}
