import { useState, useEffect, useCallback } from 'react'

export const UI_THEME_VALUES = ['stellaris-cyan', 'tactica-green', 'command-amber'] as const
export type UiTheme = (typeof UI_THEME_VALUES)[number]
export const DEFAULT_UI_THEME: UiTheme = 'stellaris-cyan'

export function normalizeUiTheme(rawValue: unknown): UiTheme {
  if (typeof rawValue !== 'string') return DEFAULT_UI_THEME
  if (rawValue === 'tactica-phosphor') return 'tactica-green'
  return (UI_THEME_VALUES as readonly string[]).includes(rawValue)
    ? rawValue as UiTheme
    : DEFAULT_UI_THEME
}

export interface Settings {
  googleApiKey: string
  googleApiKeySet: boolean
  discordToken: string
  discordTokenSet: boolean
  saveDir: string
  // Deprecated (backwards-compat with older main process / renderer builds)
  savePath?: string
  discordEnabled: boolean
  uiScale: number
  uiTheme: UiTheme
}

export interface UseSettingsResult {
  settings: Settings | null
  loading: boolean
  saving: boolean
  error: string | null
  saveSettings: (newSettings: Partial<Settings>) => Promise<boolean>
  showFolderDialog: () => Promise<string | null>
  reload: () => Promise<void>
}

export function useSettings(): UseSettingsResult {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadSettings = useCallback(async () => {
    if (!window.electronAPI) {
      setError('Electron API not available')
      setLoading(false)
      return
    }

    try {
      const loaded = await window.electronAPI.getSettings() as Settings & { uiTheme?: unknown }
      const parsedUiScale = Number(loaded.uiScale)
      const normalized: Settings = {
        ...loaded,
        saveDir: loaded.saveDir || loaded.savePath || '',
        uiScale: Number.isFinite(parsedUiScale) ? parsedUiScale : 1,
        uiTheme: normalizeUiTheme(loaded.uiTheme),
      }
      setSettings(normalized)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSettings()
  }, [loadSettings])

  const saveSettings = useCallback(async (newSettings: Partial<Settings>): Promise<boolean> => {
    if (!window.electronAPI) {
      setError('Electron API not available')
      return false
    }

    setSaving(true)
    setError(null)

    try {
      await window.electronAPI.saveSettings(newSettings)

      // Update local state with new values
      // For masked secrets, if a new value was provided (not masked), update the "Set" flag
      setSettings((prev) => {
        if (!prev) return null

        const updated = { ...prev, ...newSettings }

        // If googleApiKey was changed (not masked), update the Set flag
        if (newSettings.googleApiKey !== undefined && !newSettings.googleApiKey.includes('...')) {
          updated.googleApiKeySet = !!newSettings.googleApiKey
        }

        // If discordToken was changed (not masked), update the Set flag
        if (newSettings.discordToken !== undefined && !newSettings.discordToken.includes('...')) {
          updated.discordTokenSet = !!newSettings.discordToken
        }

        return updated
      })

      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save settings')
      return false
    } finally {
      setSaving(false)
    }
  }, [])

  const showFolderDialog = useCallback(async (): Promise<string | null> => {
    if (!window.electronAPI) {
      return null
    }

    try {
      return await window.electronAPI.showFolderDialog()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to open folder dialog')
      return null
    }
  }, [])

  return {
    settings,
    loading,
    saving,
    error,
    saveSettings,
    showFolderDialog,
    reload: loadSettings,
  }
}

export default useSettings
