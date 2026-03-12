type ThemeToggleProps = {
  dark: boolean
  onToggle: () => void
}

const THEME_STORAGE_KEY = 'theme'

function setDocumentTheme(dark: boolean) {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

export function getInitialDarkMode(): boolean {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) !== 'light'
  } catch {
    return true
  }
}

export function initializeThemePreference() {
  setDocumentTheme(getInitialDarkMode())
}

export function applyThemePreference(dark: boolean) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, dark ? 'dark' : 'light')
  } catch {}
  setDocumentTheme(dark)
}

export default function ThemeToggle({ dark, onToggle }: ThemeToggleProps) {
  return (
    <button className="btn" onClick={onToggle}>
      {dark ? 'Light' : 'Dark'}
    </button>
  )
}
