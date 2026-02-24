import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

const container = document.getElementById('root')!
const root = createRoot(container)
root.render(<App />)

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    const serviceWorkerUrl = `/service-worker.js?v=${encodeURIComponent(__AIRQMON_BUILD_ID__)}`
    navigator.serviceWorker
      .register(serviceWorkerUrl, { updateViaCache: 'none' })
      .then((registration) => registration.update())
      .catch((error) => {
        console.error('Service worker registration failed', error)
      })
  })
}
