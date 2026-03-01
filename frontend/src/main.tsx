import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { registerAirqmonServiceWorker } from './serviceWorker'
import './styles.css'

const container = document.getElementById('root')!
const root = createRoot(container)
root.render(<App />)

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    registerAirqmonServiceWorker().catch((error) => {
      console.error('Service worker registration failed', error)
    })
  })
}
