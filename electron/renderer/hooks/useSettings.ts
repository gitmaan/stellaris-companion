import { useState, useEffect, useCallback } from 'react'

export const UI_THEME_VALUES = ['stellaris-cyan', 'tactica-green', 'command-amber'] as const
export type UiTheme = (typeof UI_THEME_VALUES)[number]
export const DEFAULT_UI_THEME: UiTheme = 'stellaris-cyan'
export const CHRONICLE_REFRESH_MODE_VALUES = ['balanced', 'enhanced'] as const
export type ChronicleRefreshMode = (typeof CHRONICLE_REFRESH_MODE_VALUES)[number]
export const DEFAULT_CHRONICLE_REFRESH_MODE: ChronicleRefreshMode = 'balanced'
export const MODEL_ROUTING_MODE_VALUES = ['quality_first', 'conserve'] as const
export type ModelRoutingMode = (typeof MODEL_ROUTING_MODE_VALUES)[number]
export const DEFAULT_MODEL_ROUTING_MODE: ModelRoutingMode = 'conserve'
export const LANGUAGE_VALUES = [
  'system',
  'en',
  'de',
  'fr',
  'es',
  'pt-BR',
  'ja',
  'zh-Hans',
  'en-XA',
] as const
export type LanguageSetting = (typeof LANGUAGE_VALUES)[number]
export type ResolvedLanguage = Exclude<LanguageSetting, 'system'>
export const DEFAULT_LANGUAGE: LanguageSetting = 'system'
export const DEFAULT_RESOLVED_LANGUAGE: ResolvedLanguage = 'en'
export const ADVISOR_PROVIDER_VALUES = [
  'gemini',
  'ollama',
  'lm_studio',
  'openrouter',
  'custom',
] as const
export type AdvisorProvider = (typeof ADVISOR_PROVIDER_VALUES)[number]
export const DEFAULT_ADVISOR_PROVIDER: AdvisorProvider = 'gemini'

export function normalizeAdvisorProvider(rawValue: unknown): AdvisorProvider {
  if (typeof rawValue !== 'string') return DEFAULT_ADVISOR_PROVIDER
  const normalized = rawValue.trim().toLowerCase().replace(/[ -]/g, '_')
  if (normalized === 'lmstudio') return 'lm_studio'
  if (normalized === 'open_router') return 'openrouter'
  if (normalized === 'openai_compatible') return 'custom'
  return (ADVISOR_PROVIDER_VALUES as readonly string[]).includes(normalized)
    ? normalized as AdvisorProvider
    : DEFAULT_ADVISOR_PROVIDER
}

export function normalizeUiTheme(rawValue: unknown): UiTheme {
  if (typeof rawValue !== 'string') return DEFAULT_UI_THEME
  if (rawValue === 'tactica-phosphor') return 'tactica-green'
  return (UI_THEME_VALUES as readonly string[]).includes(rawValue)
    ? rawValue as UiTheme
    : DEFAULT_UI_THEME
}

export function normalizeChronicleRefreshMode(rawValue: unknown): ChronicleRefreshMode {
  if (typeof rawValue !== 'string') return DEFAULT_CHRONICLE_REFRESH_MODE
  return (CHRONICLE_REFRESH_MODE_VALUES as readonly string[]).includes(rawValue)
    ? rawValue as ChronicleRefreshMode
    : DEFAULT_CHRONICLE_REFRESH_MODE
}

export function normalizeModelRoutingMode(rawValue: unknown): ModelRoutingMode {
  if (typeof rawValue !== 'string') return DEFAULT_MODEL_ROUTING_MODE
  const normalized = rawValue.replace(/-/g, '_')
  if (normalized === 'auto' || normalized === 'flash_first') return 'quality_first'
  if (normalized === 'quota_saver' || normalized === 'lite_first' || normalized === 'flash_lite_first') return 'conserve'
  return (MODEL_ROUTING_MODE_VALUES as readonly string[]).includes(normalized)
    ? normalized as ModelRoutingMode
    : DEFAULT_MODEL_ROUTING_MODE
}

export function normalizeLanguage(rawValue: unknown): LanguageSetting {
  if (typeof rawValue !== 'string') return DEFAULT_LANGUAGE
  const normalized = rawValue.trim()
  if (normalized === 'pt_BR') return 'pt-BR'
  if (normalized === 'zh-CN' || normalized === 'zh_CN' || normalized === 'zh-Hans-CN') {
    return 'zh-Hans'
  }
  return (LANGUAGE_VALUES as readonly string[]).includes(normalized)
    ? normalized as LanguageSetting
    : DEFAULT_LANGUAGE
}

export function normalizeResolvedLanguage(rawValue: unknown): ResolvedLanguage {
  const normalized = normalizeLanguage(rawValue)
  return normalized === 'system' ? DEFAULT_RESOLVED_LANGUAGE : normalized
}

export interface Settings {
  googleApiKey: string
  googleApiKeySet: boolean
  openRouterApiKey: string
  openRouterApiKeySet: boolean
  customProviderApiKey: string
  customProviderApiKeySet: boolean
  secretStorageAvailable: boolean
  secretStorageBackend: string | null
  advisorProvider: AdvisorProvider
  advisorModel: string
  advisorBaseUrl: string
  discordToken: string
  discordTokenSet: boolean
  saveDir: string
  // Deprecated (backwards-compat with older main process / renderer builds)
  savePath?: string
  // Multiplayer: pin which empire the advisor analyzes. `playerName` matches the
  // player's name in the save; `playerCountryId` overrides by country ID. Empty
  // means "use the first player entry" (single-player behavior).
  playerName: string
  playerCountryId: string
  discordEnabled: boolean
  uiScale: number
  uiTheme: UiTheme
  chronicleRefreshMode: ChronicleRefreshMode
  modelRoutingMode: ModelRoutingMode
  language: LanguageSetting
  resolvedLanguage: ResolvedLanguage
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
      const loaded = await window.electronAPI.getSettings() as Settings & {
        uiTheme?: unknown
        chronicleRefreshMode?: unknown
        modelRoutingMode?: unknown
        language?: unknown
        resolvedLanguage?: unknown
        advisorProvider?: unknown
      }
      const parsedUiScale = Number(loaded.uiScale)
      const normalized: Settings = {
        ...loaded,
        saveDir: loaded.saveDir || loaded.savePath || '',
        playerName: loaded.playerName || '',
        playerCountryId: loaded.playerCountryId ? String(loaded.playerCountryId) : '',
        uiScale: Number.isFinite(parsedUiScale) ? parsedUiScale : 1,
        uiTheme: normalizeUiTheme(loaded.uiTheme),
        chronicleRefreshMode: normalizeChronicleRefreshMode(loaded.chronicleRefreshMode),
        modelRoutingMode: normalizeModelRoutingMode(loaded.modelRoutingMode),
        language: normalizeLanguage(loaded.language),
        resolvedLanguage: normalizeResolvedLanguage(loaded.resolvedLanguage),
        advisorProvider: normalizeAdvisorProvider(loaded.advisorProvider),
        advisorModel: loaded.advisorModel || '',
        advisorBaseUrl: loaded.advisorBaseUrl || '',
        openRouterApiKey: loaded.openRouterApiKey || '',
        openRouterApiKeySet: !!loaded.openRouterApiKeySet,
        customProviderApiKey: loaded.customProviderApiKey || '',
        customProviderApiKeySet: !!loaded.customProviderApiKeySet,
        secretStorageAvailable: loaded.secretStorageAvailable !== false,
        secretStorageBackend: loaded.secretStorageBackend || null,
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

        if (newSettings.openRouterApiKey !== undefined && !newSettings.openRouterApiKey.includes('...')) {
          updated.openRouterApiKeySet = !!newSettings.openRouterApiKey
        }

        if (newSettings.customProviderApiKey !== undefined && !newSettings.customProviderApiKey.includes('...')) {
          updated.customProviderApiKeySet = !!newSettings.customProviderApiKey
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
