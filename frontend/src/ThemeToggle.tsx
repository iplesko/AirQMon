import { useEffect } from 'react'

type ThemeToggleProps = {
  dark: boolean
  onToggle: () => void
}

const THEME_STORAGE_KEY = 'theme'

export function getInitialDarkMode(): boolean {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) !== 'light'
  } catch {
    return true
  }
}

function applyThemeVars(dark: boolean) {
  const root = document.documentElement.style
  if (dark) {
    root.setProperty('--bg', '#0f1723')
    root.setProperty('--card', '#0b1220')
    root.setProperty('--muted', '#94a3b8')
    root.setProperty('--text', '#e6eef8')
    root.setProperty('--accent', '#37b6ff')
    root.setProperty('--glass', 'rgba(255,255,255,0.03)')
    root.setProperty('--bg2', '#071022')
    return
  }

  root.setProperty('--bg', '#f6f8fb')
  root.setProperty('--card', '#ffffff')
  root.setProperty('--muted', '#556070')
  root.setProperty('--text', '#0b1b2b')
  root.setProperty('--accent', '#0ea5ff')
  root.setProperty('--glass', 'rgba(11,27,43,0.03)')
  root.setProperty('--bg2', '#ffffff')
}

export default function ThemeToggle({ dark, onToggle }: ThemeToggleProps) {
  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, dark ? 'dark' : 'light')
    } catch {}
    applyThemeVars(dark)
  }, [dark])

  return (
    <button className="btn" onClick={onToggle}>
      {dark ? 'Light' : 'Dark'}
    </button>
  )
}
