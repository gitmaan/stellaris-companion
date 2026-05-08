import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DEFAULT_CHRONICLE_REFRESH_MODE,
  DEFAULT_LANGUAGE,
  DEFAULT_MODEL_ROUTING_MODE,
  DEFAULT_UI_THEME,
  normalizeChronicleRefreshMode,
  normalizeLanguage,
  normalizeModelRoutingMode,
  normalizeResolvedLanguage,
  normalizeUiTheme,
  type ChronicleRefreshMode,
  type LanguageSetting,
  type ModelRoutingMode,
  type ResolvedLanguage,
  type UiTheme,
  useSettings,
} from '../hooks/useSettings'
import { LANGUAGE_OPTIONS } from '../i18n/languages'
import { useDiscord } from '../hooks/useDiscord'
import { HUDHeader, HUDSectionTitle, HUDMicro, HUDLabel } from '../components/hud/HUDText'
import { HUDPanel } from '../components/hud/HUDPanel'
import { HUDInput } from '../components/hud/HUDInput'
import { HUDButton } from '../components/hud/HUDButton'
import { HUDSelect } from '../components/hud/HUDForm'
import { useToast } from '../components/Toast'
import type { McpRelayHealthResult, McpRelayStatus } from '../global'

/**
 * DISC-017: Convert technical error messages to user-friendly messages.
 */
function getUserFriendlyErrorMessage(error: string | null, t: (key: string) => string): string | null {
  if (!error) return null
  if (error.toLowerCase().includes('cancel') || error.includes('Authorization timeout')) return t('settings.discordErrors.cancelled')
  if (error.includes('expired')) return t('settings.discordErrors.expired')
  if (error.toLowerCase().includes('auth')) return t('settings.discordErrors.auth')
  if (error.includes('connect')) return t('settings.discordErrors.connection')
  return t('settings.discordErrors.generic')
}

interface SettingsPageProps {
  onReportIssue?: () => void
  onThemeChange?: (theme: UiTheme) => void
  onChronicleRefreshModeChange?: (mode: ChronicleRefreshMode) => void
  onModelRoutingModeChange?: (mode: ModelRoutingMode) => void
  onLanguageChange?: (language: ResolvedLanguage) => void
}

const UI_SCALE_OPTIONS = [
  { value: '1', label: '100%' },
  { value: '1.1', label: '110%' },
  { value: '1.25', label: '125%' },
  { value: '1.4', label: '140%' },
]

const UI_THEME_OPTIONS: { value: UiTheme; label: string }[] = [
  { value: 'stellaris-cyan', label: 'Ion Cyan' },
  { value: 'tactica-green', label: 'Tactica Green' },
  { value: 'command-amber', label: 'Command Amber' },
]

const UI_THEME_LABELS: Record<UiTheme, string> = {
  'stellaris-cyan': 'Ion Cyan',
  'tactica-green': 'Tactica Green',
  'command-amber': 'Command Amber',
}

type GeminiQuotaMode = 'standard' | 'higher'

const GEMINI_QUOTA_MODES: GeminiQuotaMode[] = ['standard', 'higher']

function quotaModeToRoutingMode(mode: GeminiQuotaMode): ModelRoutingMode {
  return mode === 'higher' ? 'quality_first' : 'conserve'
}

function routingModeToQuotaMode(mode: ModelRoutingMode): GeminiQuotaMode {
  return mode === 'quality_first' ? 'higher' : 'standard'
}

function SettingsPage({
  onReportIssue,
  onThemeChange,
  onChronicleRefreshModeChange,
  onModelRoutingModeChange,
  onLanguageChange,
}: SettingsPageProps) {
  const { t } = useTranslation()
  const { settings, loading, saving, error, saveSettings, showFolderDialog } = useSettings()
  const { showToast } = useToast()

  const {
    status: discordStatus,
    relayStatus: discordRelayStatus,
    loading: discordLoading,
    connecting: discordConnecting,
    error: discordError,
    connectDiscord,
    disconnectDiscord,
  } = useDiscord()

  const [googleApiKey, setGoogleApiKey] = useState('')
  const [saveDir, setSaveDir] = useState('')
  const [uiScale, setUiScale] = useState(1)
  const [uiScaleSaving, setUiScaleSaving] = useState(false)
  const [uiTheme, setUiTheme] = useState<UiTheme>(DEFAULT_UI_THEME)
  const [uiThemeSaving, setUiThemeSaving] = useState(false)
  const [chronicleRefreshMode, setChronicleRefreshMode] = useState<ChronicleRefreshMode>(
    DEFAULT_CHRONICLE_REFRESH_MODE,
  )
  const [chronicleRefreshModeSaving, setChronicleRefreshModeSaving] = useState(false)
  const [modelRoutingMode, setModelRoutingMode] = useState<ModelRoutingMode>(
    DEFAULT_MODEL_ROUTING_MODE,
  )
  const [modelRoutingModeSaving, setModelRoutingModeSaving] = useState(false)
  const [language, setLanguage] = useState<LanguageSetting>(DEFAULT_LANGUAGE)
  const [languageSaving, setLanguageSaving] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [mcpRelayStatus, setMcpRelayStatus] = useState<McpRelayStatus | null>(null)
  const [mcpRelayHealth, setMcpRelayHealth] = useState<McpRelayHealthResult | null>(null)
  const [mcpRelayLoading, setMcpRelayLoading] = useState(false)
  const [mcpRelayChecking, setMcpRelayChecking] = useState(false)
  const [mcpRelayInstalling, setMcpRelayInstalling] = useState(false)
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (settings) {
      setGoogleApiKey(settings.googleApiKeySet ? settings.googleApiKey : '')
      setSaveDir(settings.saveDir || '')
      setUiScale(settings.uiScale || 1)
      const normalizedTheme = normalizeUiTheme(settings.uiTheme)
      const normalizedChronicleRefreshMode = normalizeChronicleRefreshMode(
        settings.chronicleRefreshMode,
      )
      const normalizedModelRoutingMode = normalizeModelRoutingMode(settings.modelRoutingMode)
      const normalizedLanguage = normalizeLanguage(settings.language)
      const normalizedResolvedLanguage = normalizeResolvedLanguage(settings.resolvedLanguage)
      setUiTheme(normalizedTheme)
      setChronicleRefreshMode(normalizedChronicleRefreshMode)
      setModelRoutingMode(normalizedModelRoutingMode)
      setLanguage(normalizedLanguage)
      onThemeChange?.(normalizedTheme)
      onChronicleRefreshModeChange?.(normalizedChronicleRefreshMode)
      onModelRoutingModeChange?.(normalizedModelRoutingMode)
      onLanguageChange?.(normalizedResolvedLanguage)
    }
  }, [onChronicleRefreshModeChange, onLanguageChange, onModelRoutingModeChange, onThemeChange, settings])

  useEffect(() => {
    if (!settings) return
    const hasApiKeyChange = settings.googleApiKeySet ? googleApiKey !== settings.googleApiKey : googleApiKey !== ''
    const hasPathChange = saveDir !== (settings.saveDir || '')
    setHasChanges(hasApiKeyChange || hasPathChange)
  }, [googleApiKey, saveDir, settings])

  useEffect(() => {
    let cancelled = false
    const loadMcpRelayStatus = async () => {
      if (!window.electronAPI?.mcpRelay?.status) return
      setMcpRelayLoading(true)
      try {
        const status = await window.electronAPI.mcpRelay.status()
        if (!cancelled) setMcpRelayStatus(status)
      } catch {
        if (!cancelled) setMcpRelayStatus(null)
      } finally {
        if (!cancelled) setMcpRelayLoading(false)
      }
    }
    void loadMcpRelayStatus()
    return () => {
      cancelled = true
    }
  }, [])

  const handleBrowse = async () => {
    const selectedPath = await showFolderDialog()
    if (selectedPath) setSaveDir(selectedPath)
  }

  const handleSave = async () => {
    setSaveSuccess(false)
    const settingsToSave: Record<string, string | boolean> = { saveDir }
    if (!googleApiKey.includes('...')) {
      settingsToSave.googleApiKey = googleApiKey
    }

    const success = await saveSettings(settingsToSave)
    if (success) {
      setSaveSuccess(true)
      setHasChanges(false)
      successTimeoutRef.current = setTimeout(() => setSaveSuccess(false), 3000)
    }
  }

  const handleConnectDiscord = async () => { await connectDiscord() }
  const handleDisconnectDiscord = async () => { await disconnectDiscord() }

  const refreshMcpRelayStatus = async () => {
    if (!window.electronAPI?.mcpRelay?.status) return null
    const status = await window.electronAPI.mcpRelay.status()
    setMcpRelayStatus(status)
    return status
  }

  const handleMcpRelayHealthCheck = async () => {
    if (!window.electronAPI?.mcpRelay?.healthCheck) return
    setMcpRelayChecking(true)
    try {
      const result = await window.electronAPI.mcpRelay.healthCheck()
      setMcpRelayHealth(result)
      showToast({
        type: result.ok ? 'success' : 'error',
        message: result.ok ? t('settings.mcpRelay.healthSuccess') : result.message,
        duration: result.ok ? 2200 : 5000,
      })
      await refreshMcpRelayStatus()
    } catch (e) {
      const message = e instanceof Error ? e.message : t('settings.mcpRelay.healthError')
      setMcpRelayHealth({ ok: false, message })
      showToast({ type: 'error', message, duration: 5000 })
    } finally {
      setMcpRelayChecking(false)
    }
  }

  const handleCopyMcpRelayText = async (text: string | undefined, label: string) => {
    if (!text || !window.electronAPI?.copyToClipboard) return
    const result = await window.electronAPI.copyToClipboard(text)
    showToast({
      type: result?.success ? 'success' : 'error',
      message: result?.success
        ? t('settings.mcpRelay.copySuccess', { target: label })
        : t('settings.mcpRelay.copyError'),
      duration: result?.success ? 1800 : 4000,
    })
  }

  const handleInstallClaudeDesktop = async () => {
    if (!window.electronAPI?.mcpRelay?.installClaudeDesktop) return
    const confirmed = window.confirm(t('settings.mcpRelay.installConfirm'))
    if (!confirmed) return
    setMcpRelayInstalling(true)
    try {
      const result = await window.electronAPI.mcpRelay.installClaudeDesktop()
      if (result.status) setMcpRelayStatus(result.status)
      if (!result.success) {
        showToast({
          type: 'error',
          message: result.error || t('settings.mcpRelay.installError'),
          duration: 6000,
        })
        return
      }
      showToast({
        type: 'success',
        message: t('settings.mcpRelay.installSuccess'),
        duration: 2500,
      })
      await refreshMcpRelayStatus()
    } catch (e) {
      showToast({
        type: 'error',
        message: e instanceof Error ? e.message : t('settings.mcpRelay.installError'),
        duration: 6000,
      })
    } finally {
      setMcpRelayInstalling(false)
    }
  }

  const [retrying, setRetrying] = useState(false)
  const handleUiScaleChange = async (rawValue: string) => {
    const nextScale = Number(rawValue)
    if (!Number.isFinite(nextScale)) return
    if (Math.abs(nextScale - uiScale) < 0.0001) return

    const previousScale = uiScale
    setUiScale(nextScale)
    setUiScaleSaving(true)

    const success = await saveSettings({ uiScale: nextScale })
    setUiScaleSaving(false)

    if (!success) {
      setUiScale(previousScale)
      showToast({
        type: 'error',
        message: t('settings.toasts.textSizeError'),
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: t('settings.toasts.textSizeSuccess', { percent: Math.round(nextScale * 100) }),
      duration: 1800,
    })
  }

  const handleUiThemeChange = async (rawValue: string) => {
    const nextTheme = normalizeUiTheme(rawValue)
    if (nextTheme === uiTheme) return

    const previousTheme = uiTheme
    setUiTheme(nextTheme)
    onThemeChange?.(nextTheme)
    setUiThemeSaving(true)

    const success = await saveSettings({ uiTheme: nextTheme })
    setUiThemeSaving(false)

    if (!success) {
      setUiTheme(previousTheme)
      onThemeChange?.(previousTheme)
      showToast({
        type: 'error',
        message: t('settings.toasts.themeError'),
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: t('settings.toasts.themeSuccess', { theme: UI_THEME_LABELS[nextTheme] }),
      duration: 1800,
    })
  }

  const handleChronicleRefreshModeChange = async (rawValue: string) => {
    const nextMode = normalizeChronicleRefreshMode(rawValue)
    if (nextMode === chronicleRefreshMode) return

    const previousMode = chronicleRefreshMode
    setChronicleRefreshMode(nextMode)
    onChronicleRefreshModeChange?.(nextMode)
    setChronicleRefreshModeSaving(true)

    const success = await saveSettings({ chronicleRefreshMode: nextMode })
    setChronicleRefreshModeSaving(false)

    if (!success) {
      setChronicleRefreshMode(previousMode)
      onChronicleRefreshModeChange?.(previousMode)
      showToast({
        type: 'error',
        message: t('settings.chronicleRefresh.toastError'),
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: t('settings.chronicleRefresh.toastSuccess', {
        mode: t(`settings.chronicleRefresh.${nextMode}`),
      }),
      duration: 1800,
    })
  }

  const handleModelRoutingModeChange = async (rawValue: string) => {
    const nextMode = normalizeModelRoutingMode(rawValue)
    if (nextMode === modelRoutingMode) return

    const previousMode = modelRoutingMode
    setModelRoutingMode(nextMode)
    onModelRoutingModeChange?.(nextMode)
    setModelRoutingModeSaving(true)

    const success = await saveSettings({ modelRoutingMode: nextMode })
    setModelRoutingModeSaving(false)

    if (!success) {
      setModelRoutingMode(previousMode)
      onModelRoutingModeChange?.(previousMode)
      showToast({
        type: 'error',
        message: t('settings.modelRouting.toastError'),
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: t('settings.modelRouting.toastSuccess', {
        mode: t(`settings.modelRouting.${nextMode === 'quality_first' ? 'qualityFirst' : 'conserve'}`),
      }),
      duration: 1800,
    })
  }

  const handleGeminiQuotaModeChange = async (nextQuotaMode: GeminiQuotaMode) => {
    await handleModelRoutingModeChange(quotaModeToRoutingMode(nextQuotaMode))
  }

  const handleLanguageChange = async (rawValue: string) => {
    const nextLanguage = normalizeLanguage(rawValue)
    if (nextLanguage === language) return

    const previousLanguage = language
    setLanguage(nextLanguage)
    setLanguageSaving(true)

    const success = await saveSettings({ language: nextLanguage })
    setLanguageSaving(false)

    if (!success) {
      setLanguage(previousLanguage)
      showToast({
        type: 'error',
        message: t('settings.toasts.languageError'),
        duration: 4000,
      })
      return
    }

    try {
      const loaded = await window.electronAPI?.getSettings()
      const loadedLanguage = normalizeLanguage((loaded as { language?: unknown } | undefined)?.language)
      const loadedResolved = normalizeResolvedLanguage(
        (loaded as { resolvedLanguage?: unknown } | undefined)?.resolvedLanguage,
      )
      setLanguage(loadedLanguage)
      onLanguageChange?.(loadedResolved)
    } catch {
      onLanguageChange?.(normalizeResolvedLanguage(nextLanguage))
    }

    showToast({
      type: 'success',
      message: t('settings.toasts.languageSuccess', {
        language: t(`languages.${nextLanguage}`),
      }),
      duration: 1800,
    })
  }

  const handleRetryConnection = async () => {
    if (!window.electronAPI?.discord) return
    setRetrying(true)
    try {
      await window.electronAPI.discord.relayConnect()
    } catch (e) {
      // Error handled by status update
    } finally {
      setRetrying(false)
    }
  }

  const languageOptions = LANGUAGE_OPTIONS.map((option) => ({
    value: option.value,
    label: t(`languages.${option.value}`),
  }))

  const chronicleModeLabel = (mode: ChronicleRefreshMode) =>
    t(`settings.chronicleRefresh.${mode}`)

  const chronicleModeHelper = (mode: ChronicleRefreshMode) =>
    t(`settings.chronicleRefresh.${mode}Help`)

  const modelRoutingLabel = (mode: ModelRoutingMode) =>
    t(`settings.modelRouting.${mode === 'quality_first' ? 'qualityFirst' : 'conserve'}`)

  const modelRoutingHelper = (mode: ModelRoutingMode) =>
    t(`settings.modelRouting.${mode === 'quality_first' ? 'qualityFirstHelp' : 'conserveHelp'}`)

  const geminiQuotaMode = routingModeToQuotaMode(modelRoutingMode)
  const geminiQuotaLabel = (mode: GeminiQuotaMode) => t(`settings.geminiQuota.${mode}`)
  const geminiQuotaTag = (mode: GeminiQuotaMode) => t(`settings.geminiQuota.${mode}Tag`)
  const geminiQuotaHelper = (mode: GeminiQuotaMode) => t(`settings.geminiQuota.${mode}Help`)

  const mcpRelayReady = Boolean(mcpRelayStatus?.databaseExists)
  const mcpRelayConfigured = Boolean(mcpRelayStatus?.claudeDesktop?.configured)
  const mcpRelayCurrent = Boolean(mcpRelayStatus?.claudeDesktop?.current)
  const mcpRelaySummary = mcpRelayLoading
    ? t('settings.mcpRelay.loadingSummary')
    : mcpRelayReady
      ? t('settings.mcpRelay.readySummary')
      : t('settings.mcpRelay.noDatabaseSummary')
  const claudeDesktopStatusLabel = mcpRelayConfigured
    ? (mcpRelayCurrent ? t('settings.mcpRelay.installed') : t('settings.mcpRelay.installedNeedsRefresh'))
    : t('settings.mcpRelay.notInstalled')
  const claudeDesktopStatusClass = mcpRelayConfigured
    ? (mcpRelayCurrent ? 'text-accent-green' : 'text-accent-yellow')
    : 'text-text-secondary'
  const claudeDesktopActionLabel = mcpRelayInstalling
    ? t('settings.mcpRelay.installing')
    : mcpRelayCurrent
      ? t('settings.mcpRelay.claudeConnected')
      : mcpRelayConfigured
        ? t('settings.mcpRelay.updateClaude')
        : t('settings.mcpRelay.connectClaude')

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
           <div className="w-12 h-12 border-t-2 border-l-2 border-accent-cyan rounded-full animate-spin" />
           <HUDMicro className="animate-pulse">{t('settings.loading')}</HUDMicro>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto custom-scrollbar pr-2 pb-12">
      <div className="max-w-4xl mx-auto pt-4">
        
        {/* Header Area */}
        <div className="flex items-end justify-between mb-8">
            <div>
                <HUDMicro className="mb-1 text-accent-cyan">{t('settings.eyebrow')}</HUDMicro>
                <HUDHeader size="xl">{t('settings.title')}</HUDHeader>
            </div>
            <div className="w-[640px] max-w-[68%] grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <HUDSelect
                  label={t('settings.textSize')}
                  value={String(uiScale)}
                  disabled={uiScaleSaving}
                  onChange={(e) => void handleUiScaleChange(e.target.value)}
                  options={UI_SCALE_OPTIONS}
                />
                <HUDMicro className="block mt-1 text-right">
                  {uiScaleSaving ? t('common.applying') : 'CMD/CTRL +/-/0'}
                </HUDMicro>
              </div>
              <div>
                <HUDSelect
                  label={t('settings.colorTheme')}
                  value={uiTheme}
                  disabled={uiThemeSaving}
                  onChange={(e) => void handleUiThemeChange(e.target.value)}
                  options={UI_THEME_OPTIONS}
                />
                <HUDMicro className="block mt-1 text-right">
                  {uiThemeSaving ? t('common.applying') : t('settings.themePreset')}
                </HUDMicro>
              </div>
              <div>
                <HUDSelect
                  label={t('settings.language')}
                  value={language}
                  disabled={languageSaving}
                  onChange={(e) => void handleLanguageChange(e.target.value)}
                  options={languageOptions}
                />
                <HUDMicro className="block mt-1 text-right">
                  {languageSaving ? t('common.applying') : t('settings.languageHint')}
                </HUDMicro>
              </div>
            </div>
        </div>

        {/* Top Status Messages */}
        {error && (
            <HUDPanel variant="alert" className="mb-6 flex items-center gap-4" decoration="scanline">
                <span className="text-accent-red text-xl">⚠</span>
                <div>
                    <HUDLabel className="text-accent-red">{t('settings.systemAlert')}</HUDLabel>
                    <p className="text-accent-red/80 font-mono text-sm">{error}</p>
                </div>
            </HUDPanel>
        )}
        
        {saveSuccess && (
            <HUDPanel variant="primary" className="mb-6 border-accent-green/50" decoration="scanline">
                <div className="flex items-center gap-3">
                    <div className="w-2 h-2 bg-accent-green shadow-glow-green" />
                    <span className="font-mono text-accent-green text-sm">{t('settings.saveSuccess')}</span>
                </div>
            </HUDPanel>
        )}

        {/* Main Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            
            {/* Column 1: Core Systems */}
            <div className="space-y-8">
                
                {/* API Section */}
                <section>
                    <HUDSectionTitle number="01">{t('settings.sections.intelligence')}</HUDSectionTitle>
                    <HUDPanel decoration="tech" title={t('settings.panels.geminiAccess')}>
                        <div className="space-y-4 pt-2">
                             <HUDInput 
                                label={t('settings.api.label')}
                                type="password"
                                value={googleApiKey}
                                onChange={(e) => setGoogleApiKey(e.target.value)}
                                placeholder={settings?.googleApiKeySet ? t('settings.api.placeholderSet') : t('settings.api.placeholderEmpty')}
                             />
                             <div className="flex justify-between items-center">
                                 <span className="font-mono text-xs text-white/30">
                                     {t('settings.api.status')} {settings?.googleApiKeySet ? <span className="text-accent-green">{t('settings.api.active')}</span> : <span className="text-accent-yellow">{t('settings.api.missing')}</span>}
                                 </span>
                                 <a 
                                    href="https://aistudio.google.com/app/apikey" 
                                    target="_blank" 
                                    rel="noreferrer"
                                    className="font-display text-[10px] text-accent-cyan hover:underline tracking-wider"
                                 >
                                     {t('settings.api.generateKey')}
                                 </a>
                             </div>
                             <div className="border-t border-white/10 pt-4 space-y-3">
                                 <div className="flex items-center justify-between gap-3">
                                     <HUDLabel>{t('settings.geminiQuota.label')}</HUDLabel>
                                     {modelRoutingModeSaving && (
                                       <HUDMicro className="text-right">{t('common.applying')}</HUDMicro>
                                     )}
                                 </div>
                                 <HUDMicro className="block leading-relaxed text-white/45 normal-case tracking-[0.08em]">
                                   {t('settings.geminiQuota.description')}
                                 </HUDMicro>

                                 <div className="grid grid-cols-2 gap-2 rounded-sm border border-white/10 bg-black/20 p-1">
                                   {GEMINI_QUOTA_MODES.map((mode) => {
                                     const isSelected = geminiQuotaMode === mode
                                     return (
                                       <button
                                         key={mode}
                                         type="button"
                                         disabled={modelRoutingModeSaving}
                                         aria-pressed={isSelected}
                                         aria-label={t('settings.geminiQuota.aria', { mode: geminiQuotaLabel(mode) })}
                                         onClick={() => void handleGeminiQuotaModeChange(mode)}
                                         className={`relative rounded-sm px-3 py-2 text-left transition-all duration-200 ${
                                           isSelected
                                             ? 'border border-accent-cyan/60 bg-accent-cyan/12 text-accent-cyan shadow-glow-sm'
                                             : 'border border-transparent bg-transparent text-text-secondary hover:border-white/15 hover:bg-white/5 hover:text-text-primary'
                                         } disabled:opacity-50 disabled:cursor-not-allowed`}
                                       >
                                         <div className="font-display text-[11px] uppercase tracking-[0.18em]">
                                           {geminiQuotaLabel(mode)}
                                         </div>
                                         <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-white/35">
                                           {geminiQuotaTag(mode)}
                                         </div>
                                       </button>
                                     )
                                   })}
                                 </div>

                                 <HUDMicro className="block leading-relaxed text-white/45 normal-case tracking-[0.08em]">
                                   {geminiQuotaHelper(geminiQuotaMode)}
                                 </HUDMicro>

                                 <details className="group border-t border-white/10 pt-3">
                                   <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-sm border border-white/10 bg-black/20 px-3 py-2 font-display text-[10px] uppercase tracking-[0.18em] text-text-secondary transition-all duration-200 hover:border-accent-cyan/40 hover:bg-accent-cyan/5 hover:text-accent-cyan">
                                     <span className="flex items-center gap-2">
                                       <span className="transition-transform duration-200 group-open:rotate-90">&gt;</span>
                                       <span className="group-open:hidden">{t('settings.geminiQuota.showAdvanced')}</span>
                                       <span className="hidden group-open:inline">{t('settings.geminiQuota.hideAdvanced')}</span>
                                     </span>
                                     <span className="font-mono text-[9px] tracking-[0.12em] text-white/35">
                                       {t('settings.geminiQuota.optional')}
                                     </span>
                                   </summary>
                                   <div className="mt-3 space-y-4">
                                     <div className="space-y-3">
                                       <div className="flex items-center justify-between gap-3">
                                         <HUDLabel>{t('settings.modelRouting.label')}</HUDLabel>
                                         {modelRoutingModeSaving && (
                                           <HUDMicro className="text-right">{t('common.applying')}</HUDMicro>
                                         )}
                                       </div>

                                       <div className="grid grid-cols-2 gap-2 rounded-sm border border-white/10 bg-black/20 p-1">
                                         {(['quality_first', 'conserve'] as const).map((mode) => {
                                           const isSelected = modelRoutingMode === mode
                                           return (
                                             <button
                                               key={mode}
                                               type="button"
                                               disabled={modelRoutingModeSaving}
                                               aria-pressed={isSelected}
                                               aria-label={t('settings.modelRouting.toastSuccess', { mode: modelRoutingLabel(mode) })}
                                               onClick={() => void handleModelRoutingModeChange(mode)}
                                               className={`relative rounded-sm px-3 py-2 text-left transition-all duration-200 ${
                                                 isSelected
                                                   ? 'border border-accent-cyan/60 bg-accent-cyan/12 text-accent-cyan shadow-glow-sm'
                                                   : 'border border-transparent bg-transparent text-text-secondary hover:border-white/15 hover:bg-white/5 hover:text-text-primary'
                                               } disabled:opacity-50 disabled:cursor-not-allowed`}
                                             >
                                               <div className="font-display text-[11px] uppercase tracking-[0.18em]">
                                                 {modelRoutingLabel(mode)}
                                               </div>
                                               <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-white/35">
                                                 {mode === 'quality_first'
                                                   ? t('settings.modelRouting.qualityFirstTag')
                                                   : t('settings.modelRouting.conserveTag')}
                                               </div>
                                             </button>
                                           )
                                         })}
                                       </div>

                                       <HUDMicro className="block leading-relaxed text-white/45 normal-case tracking-[0.08em]">
                                         {modelRoutingHelper(modelRoutingMode)}
                                       </HUDMicro>
                                     </div>

                                     <div className="space-y-3">
                                       <div className="flex items-center justify-between gap-3">
                                         <HUDLabel>{t('settings.chronicleRefresh.label')}</HUDLabel>
                                         {chronicleRefreshModeSaving && (
                                           <HUDMicro className="text-right">{t('common.applying')}</HUDMicro>
                                         )}
                                       </div>

                                       <div className="grid grid-cols-2 gap-2 rounded-sm border border-white/10 bg-black/20 p-1">
                                         {(['balanced', 'enhanced'] as const).map((mode) => {
                                           const isSelected = chronicleRefreshMode === mode
                                           return (
                                             <button
                                               key={mode}
                                               type="button"
                                               disabled={chronicleRefreshModeSaving}
                                               aria-pressed={isSelected}
                                               aria-label={t('settings.chronicleRefresh.aria', { mode: chronicleModeLabel(mode) })}
                                               onClick={() => void handleChronicleRefreshModeChange(mode)}
                                               className={`relative rounded-sm px-3 py-2 text-left transition-all duration-200 ${
                                                 isSelected
                                                   ? 'border border-accent-cyan/60 bg-accent-cyan/12 text-accent-cyan shadow-glow-sm'
                                                   : 'border border-transparent bg-transparent text-text-secondary hover:border-white/15 hover:bg-white/5 hover:text-text-primary'
                                               } disabled:opacity-50 disabled:cursor-not-allowed`}
                                             >
                                               <div className="font-display text-[11px] uppercase tracking-[0.18em]">
                                                 {chronicleModeLabel(mode)}
                                               </div>
                                               <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-white/35">
                                                 {mode === 'balanced' ? t('settings.chronicleRefresh.balancedTag') : t('settings.chronicleRefresh.enhancedTag')}
                                               </div>
                                             </button>
                                           )
                                         })}
                                       </div>

                                       <HUDMicro className="block leading-relaxed text-white/45 normal-case tracking-[0.08em]">
                                         {chronicleModeHelper(chronicleRefreshMode)}
                                       </HUDMicro>
                                     </div>
                                   </div>
                                 </details>
                             </div>
                        </div>
                    </HUDPanel>
                </section>

                {/* Save Data Section */}
                <section>
                    <HUDSectionTitle number="02">{t('settings.sections.data')}</HUDSectionTitle>
                    <HUDPanel decoration="brackets" title={t('settings.panels.saveSource')}>
                         <div className="space-y-4 pt-2">
                             <div className="flex gap-2 items-end">
                                 <HUDInput 
                                    className="flex-1"
                                    label={t('settings.saveData.directoryLabel')}
                                    value={saveDir}
                                    onChange={(e) => setSaveDir(e.target.value)}
                                    placeholder={t('settings.saveData.placeholder')}
                                    readOnly
                                 />
                                 <HUDButton variant="secondary" onClick={handleBrowse} className="mb-[1px]">
                                     {t('common.browse')}
                                 </HUDButton>
                             </div>
                             <HUDMicro className="block mt-2">
                                 {t('settings.saveData.target')}
                             </HUDMicro>
                         </div>
                    </HUDPanel>
                </section>

            </div>

            {/* Column 2: Comms & Feedback */}
            <div className="space-y-8">
                {/* MCP Relay Section */}
                <section>
                    <HUDSectionTitle number="03">{t('settings.sections.mcpRelay')}</HUDSectionTitle>
                    <HUDPanel
                      decoration="tech"
                      variant={mcpRelayReady ? 'primary' : 'secondary'}
                      title={t('settings.panels.mcpRelay')}
                    >
                        <div className="space-y-4 pt-2">
                            <div className="border border-white/10 bg-white/5 p-3 rounded-sm space-y-2">
                                <div className="flex items-center justify-between gap-3">
                                  <HUDLabel>{t('settings.mcpRelay.claudeDesktop')}</HUDLabel>
                                  <div className={`font-display text-[11px] tracking-wider ${claudeDesktopStatusClass}`}>
                                    {claudeDesktopStatusLabel}
                                  </div>
                                </div>
                                <p className="font-mono text-[10px] leading-relaxed text-white/45">
                                  {mcpRelaySummary}
                                </p>
                                {mcpRelayStatus?.claudeDesktop?.error && (
                                  <p className="font-mono text-[10px] leading-relaxed text-accent-red">
                                    {mcpRelayStatus.claudeDesktop.error}
                                  </p>
                                )}
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                <HUDButton
                                  variant="primary"
                                  onClick={() => void handleInstallClaudeDesktop()}
                                  disabled={mcpRelayInstalling || !mcpRelayStatus || mcpRelayCurrent}
                                  className="px-3 text-[9px]"
                                >
                                  {claudeDesktopActionLabel}
                                </HUDButton>
                                <HUDButton
                                  variant="secondary"
                                  onClick={() => void handleCopyMcpRelayText(mcpRelayStatus?.snippets?.codex, 'Codex')}
                                  disabled={!mcpRelayStatus}
                                  className="px-3 text-[9px]"
                                >
                                  {t('settings.mcpRelay.copyCodexSetup')}
                                </HUDButton>
                            </div>

                            <div className="border-t border-white/10 pt-3 space-y-1">
                              <HUDLabel>{t('settings.mcpRelay.otherApps')}</HUDLabel>
                              <HUDMicro className="block leading-relaxed text-white/45 normal-case tracking-[0.08em]">
                                {t('settings.mcpRelay.otherAppsHelp')}
                              </HUDMicro>
                            </div>

                            <details className="group">
                              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-sm border border-white/10 bg-black/20 px-3 py-2 font-display text-[10px] uppercase tracking-[0.18em] text-text-secondary transition-all duration-200 hover:border-accent-cyan/40 hover:bg-accent-cyan/5 hover:text-accent-cyan">
                                <span className="flex items-center gap-2">
                                  <span className="transition-transform duration-200 group-open:rotate-90">&gt;</span>
                                  <span className="group-open:hidden">{t('settings.mcpRelay.showAdvancedSetup')}</span>
                                  <span className="hidden group-open:inline">{t('settings.mcpRelay.hideAdvancedSetup')}</span>
                                </span>
                                <span className="font-mono text-[9px] tracking-[0.12em] text-white/35">
                                  {t('settings.mcpRelay.optional')}
                                </span>
                              </summary>
                              <div className="mt-3 space-y-3">
                                <div className="border border-white/10 bg-black/20 p-3 rounded-sm space-y-2">
                                  <div className="flex items-center justify-between gap-3">
                                    <HUDLabel>{t('settings.mcpRelay.localEndpoint')}</HUDLabel>
                                    <HUDMicro>{mcpRelayStatus?.language?.toUpperCase() || 'EN'}</HUDMicro>
                                  </div>
                                  <p className="font-mono text-[10px] leading-relaxed text-white/45 break-all">
                                    {mcpRelayStatus?.dbPath || t('settings.mcpRelay.loading')}
                                  </p>
                                  {mcpRelayHealth && (
                                    <p className={`font-mono text-[10px] leading-relaxed ${mcpRelayHealth.ok ? 'text-accent-green' : 'text-accent-red'}`}>
                                      {mcpRelayHealth.message}
                                    </p>
                                  )}
                                </div>

                                <div className="grid grid-cols-2 gap-2">
                                  <HUDButton
                                    variant="secondary"
                                    onClick={() => void handleMcpRelayHealthCheck()}
                                    disabled={mcpRelayChecking}
                                    className="px-3 text-[9px]"
                                  >
                                    {mcpRelayChecking ? t('settings.mcpRelay.checking') : t('settings.mcpRelay.runCheck')}
                                  </HUDButton>
                                  <HUDButton
                                    variant="secondary"
                                    onClick={() => void handleCopyMcpRelayText(mcpRelayStatus?.snippets?.claudeDesktop, 'Claude Desktop')}
                                    disabled={!mcpRelayStatus}
                                    className="px-3 text-[9px]"
                                  >
                                    {t('settings.mcpRelay.copyClaude')}
                                  </HUDButton>
                                  <HUDButton
                                    variant="secondary"
                                    onClick={() => void handleCopyMcpRelayText(mcpRelayStatus?.snippets?.claudeCode, 'Claude Code')}
                                    disabled={!mcpRelayStatus}
                                    className="px-3 text-[9px]"
                                  >
                                    {t('settings.mcpRelay.copyClaudeCode')}
                                  </HUDButton>
                                  <HUDButton
                                    variant="secondary"
                                    onClick={() => void handleCopyMcpRelayText(mcpRelayStatus?.snippets?.genericJson, 'MCP JSON')}
                                    disabled={!mcpRelayStatus}
                                    className="px-3 text-[9px]"
                                  >
                                    {t('settings.mcpRelay.copyMcpJson')}
                                  </HUDButton>
                                  <HUDButton
                                    variant="ghost"
                                    onClick={() => void window.electronAPI?.mcpRelay?.openClaudeConfigFolder?.()}
                                    disabled={!mcpRelayStatus?.claudeDesktop?.configPath}
                                    className="col-span-2 px-3 text-[9px]"
                                  >
                                    {t('settings.mcpRelay.revealConfig')}
                                  </HUDButton>
                                </div>
                              </div>
                            </details>

                        </div>
                    </HUDPanel>
                </section>
                
                {/* Discord Section */}
                <section>
                    <HUDSectionTitle number="04">{t('settings.sections.communications')}</HUDSectionTitle>
                    <HUDPanel decoration="scanline" variant={discordStatus?.connected ? 'primary' : 'secondary'} title={t('settings.panels.discordLink')}>
                        <div className="space-y-4 pt-2">
                            {discordLoading ? (
                                <div className="flex items-center gap-3 py-4 opacity-50">
                                    <div className="w-4 h-4 border border-accent-cyan border-t-transparent rounded-full animate-spin" />
                                    <HUDMicro>{t('settings.discord.loading')}</HUDMicro>
                                </div>
                            ) : discordStatus?.connected ? (
                                <>
                                    <div className="flex items-center gap-4 bg-white/5 p-3 rounded-sm border border-white/10">
                                        <div className="w-10 h-10 bg-discord rounded flex items-center justify-center text-white font-display text-lg">
                                            {discordStatus?.username?.charAt(0).toUpperCase()}
                                        </div>
                                        <div>
                                            <div className="font-display text-sm tracking-wide text-white">{discordStatus?.username}</div>
                                            <HUDMicro className="text-accent-green">{t('settings.discord.signalStrong')}</HUDMicro>
                                        </div>
                                    </div>
                                    
                                    <div className="grid grid-cols-2 gap-3">
                                        <HUDButton 
                                            variant="secondary" 
                                            onClick={() => window.open('https://discord.com/oauth2/authorize?client_id=1460412463282524231&scope=bot+applications.commands&permissions=0', '_blank')}
                                            className="text-[10px]"
                                        >
                                            {t('settings.discord.inviteBot')}
                                        </HUDButton>
                                        <HUDButton variant="danger" onClick={handleDisconnectDiscord} className="text-[10px]">
                                            {t('settings.discord.terminate')}
                                        </HUDButton>
                                    </div>

                                    {/* Relay Status */}
                                    {discordRelayStatus && (
                                        <div className="flex items-center justify-between border-t border-white/10 pt-3 mt-1">
                                            <span className="font-mono text-[10px] text-white/50">
                                              {t('settings.discord.relay', { state: discordRelayStatus.state.toUpperCase() })}
                                            </span>
                                            {discordRelayStatus.state === 'error' && (
                                                <button onClick={handleRetryConnection} disabled={retrying} className="text-accent-yellow hover:underline text-[10px] font-mono">
                                                    {retrying ? t('common.retrying') : t('common.retry')}
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </>
                            ) : (
                                <>
                                    <p className="font-mono text-xs text-white/60 leading-relaxed">
                                        {t('settings.discord.description')}
                                    </p>
                                    <HUDButton 
                                        variant="primary" 
                                        onClick={handleConnectDiscord}
                                        disabled={discordConnecting}
                                        className="w-full"
                                    >
                                        {discordConnecting ? t('settings.discord.connecting') : t('settings.discord.connect')}
                                    </HUDButton>
                                </>
                            )}
                            
                            {discordError && (
                                <p className="text-accent-red text-xs font-mono border-l-2 border-accent-red pl-2">
                                    {t('settings.discord.errorPrefix')} {getUserFriendlyErrorMessage(discordError, t)}
                                </p>
                            )}
                        </div>
                    </HUDPanel>
                </section>

                {/* Feedback Section */}
                <section>
                    <HUDSectionTitle number="05">{t('settings.sections.diagnostics')}</HUDSectionTitle>
                    <div className="flex gap-4 items-center p-4 border border-white/10 bg-white/5 rounded-sm">
                        <div className="flex-1">
                             <HUDLabel className="block mb-1">{t('settings.feedback.label')}</HUDLabel>
                             <p className="font-mono text-xs text-white/40">{t('settings.feedback.body')}</p>
                        </div>
                        <HUDButton variant="secondary" onClick={onReportIssue}>
                            {t('common.reportIssue')}
                        </HUDButton>
                    </div>
                </section>
            </div>
        </div>

        {/* Floating Action Bar */}
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
             <div className="bg-black/80 backdrop-blur-md border border-accent-cyan/30 px-6 py-3 rounded-full shadow-[0_0_20px_rgba(0,0,0,0.5)] flex items-center gap-6">
                 <div className="flex items-center gap-2">
                     <div className={`w-2 h-2 rounded-full ${hasChanges ? 'bg-accent-yellow animate-pulse' : 'bg-white/20'}`} />
                     <HUDMicro>{hasChanges ? t('settings.actionBar.unsaved') : t('settings.actionBar.ready')}</HUDMicro>
                 </div>
                 <div className="h-4 w-px bg-white/10" />
                 <HUDButton 
                    variant="primary" 
                    onClick={handleSave} 
                    disabled={saving || !hasChanges}
                    className="min-w-[140px]"
                 >
                     {saving ? t('settings.actionBar.committing') : t('settings.actionBar.apply')}
                 </HUDButton>
             </div>
        </div>

      </div>
    </div>
  )
}

export default SettingsPage
