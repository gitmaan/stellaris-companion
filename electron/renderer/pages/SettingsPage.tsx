import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useChatGPT } from '../hooks/useChatGPT'
import {
  DEFAULT_ADVISOR_PROVIDER,
  DEFAULT_CHRONICLE_REFRESH_MODE,
  DEFAULT_LANGUAGE,
  DEFAULT_MODEL_ROUTING_MODE,
  DEFAULT_UPDATE_CHANNEL,
  DEFAULT_UI_THEME,
  normalizeAdvisorProvider,
  normalizeChronicleRefreshMode,
  normalizeLanguage,
  normalizeModelRoutingMode,
  normalizeUpdateChannel,
  normalizeUiTheme,
  type AdvisorProvider,
  type ChronicleRefreshMode,
  type LanguageSetting,
  type ModelRoutingMode,
  type UpdateChannel,
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
import { AISetupForm } from '../components/settings/AISetupForm'
import { ChronicleRefreshControl } from '../components/settings/ChronicleRefreshControl'
import { PreferenceFeedback } from '../components/settings/PreferenceFeedback'
import { AISetupChoice, type AISetupRoute } from '../components/settings/AISetupChoice'
import { MCPRelayPanel } from '../components/settings/MCPRelayPanel'
import type { HistoryStorageResponse } from '../hooks/useBackend'

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

function revealSettingsSection(id: string) {
  const section = document.getElementById(id)
  const disclosure = section?.closest('details')
  if (disclosure) disclosure.open = true
  section?.scrollIntoView()
  section?.focus({ preventScroll: true })
}

interface SettingsPageProps {
  isActive?: boolean
  openTarget?: { id: string; request: number }
  onReportIssue?: () => void
  onThemeChange?: (theme: UiTheme) => void
  onChronicleRefreshModeChange?: (mode: ChronicleRefreshMode) => void
  onModelRoutingModeChange?: (mode: ModelRoutingMode) => void
  onLanguageSelect?: (language: LanguageSetting) => Promise<boolean>
  onOpenCampaignHistory?: () => void
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

function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes)) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
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
  isActive = true,
  openTarget,
  onReportIssue,
  onThemeChange,
  onChronicleRefreshModeChange,
  onModelRoutingModeChange,
  onLanguageSelect,
  onOpenCampaignHistory,
}: SettingsPageProps) {
  const { t } = useTranslation()
  const { settings, loading, saving, error, saveSettings, showFolderDialog, reload } = useSettings()
  const { modelRevision } = useChatGPT()
  useEffect(() => {
    if (modelRevision) void reload()
  }, [modelRevision, reload])
  const { showToast } = useToast()

  const [aiRoute, setAIRoute] = useState<AISetupRoute>('companion')

  useEffect(() => {
    if (loading || !openTarget?.request) return
    setAIRoute(openTarget.id === 'ai-app-connections' ? 'relay' : 'companion')
    const frame = requestAnimationFrame(() => revealSettingsSection(openTarget.id))
    return () => cancelAnimationFrame(frame)
  }, [loading, openTarget])

  const {
    status: discordStatus,
    relayStatus: discordRelayStatus,
    loading: discordLoading,
    connecting: discordConnecting,
    error: discordError,
    connectDiscord,
    disconnectDiscord,
  } = useDiscord()

  const [advisorProvider, setAdvisorProvider] = useState<AdvisorProvider>(DEFAULT_ADVISOR_PROVIDER)
  const [saveDir, setSaveDir] = useState('')
  const [playerName, setPlayerName] = useState('')
  const [multiplayerOpen, setMultiplayerOpen] = useState(false)
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
  const [savedPreferences, setSavedPreferences] = useState<Record<string, boolean>>({})
  const markPreferenceSaved = (name: string, saved: boolean) => setSavedPreferences(current => ({ ...current, [name]: saved }))
  const [updateChannel, setUpdateChannel] = useState<UpdateChannel>(DEFAULT_UPDATE_CHANNEL)
  const [updateChannelSaving, setUpdateChannelSaving] = useState(false)
  const [historyStorage, setHistoryStorage] = useState<HistoryStorageResponse | null>(null)
  const [historyBackupRunning, setHistoryBackupRunning] = useState(false)
  const settingsHydratedRef = useRef(false)
  useEffect(() => {
    let cancelled = false
    void window.electronAPI?.backend.historyStorage().then(result => {
      if (!cancelled && result.ok) setHistoryStorage(result.data)
    })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!settings || settingsHydratedRef.current) return
    settingsHydratedRef.current = true

    setAdvisorProvider(normalizeAdvisorProvider(settings.advisorProvider))
    setSaveDir(settings.saveDir || '')
    setPlayerName(settings.playerName || '')
    setMultiplayerOpen(Boolean(settings.playerName?.trim()))
    setUiScale(settings.uiScale || 1)
    const normalizedTheme = normalizeUiTheme(settings.uiTheme)
    const normalizedChronicleRefreshMode = normalizeChronicleRefreshMode(
      settings.chronicleRefreshMode,
    )
    const normalizedModelRoutingMode = normalizeModelRoutingMode(settings.modelRoutingMode)
    const normalizedLanguage = normalizeLanguage(settings.language)
    const normalizedUpdateChannel = normalizeUpdateChannel(settings.updateChannel)
    setUiTheme(normalizedTheme)
    setChronicleRefreshMode(normalizedChronicleRefreshMode)
    setModelRoutingMode(normalizedModelRoutingMode)
    setLanguage(normalizedLanguage)
    setUpdateChannel(normalizedUpdateChannel)
    onThemeChange?.(normalizedTheme)
    onChronicleRefreshModeChange?.(normalizedChronicleRefreshMode)
    onModelRoutingModeChange?.(normalizedModelRoutingMode)
  }, [onChronicleRefreshModeChange, onModelRoutingModeChange, onThemeChange, settings])

  const handleBrowse = async () => {
    const selectedPath = await showFolderDialog()
    if (!selectedPath) return
    const previousPath = saveDir
    setSaveDir(selectedPath)
    const success = await saveSettings({ saveDir: selectedPath })
    if (!success) {
      setSaveDir(previousPath)
      return
    }
    showToast({ type: 'success', message: t('settings.saveData.folderSaved') })
  }

  const handleUseAutomaticSaveFolder = async () => {
    const previousPath = saveDir
    setSaveDir('')
    const success = await saveSettings({ saveDir: '' })
    if (!success) {
      setSaveDir(previousPath)
      return
    }
    showToast({ type: 'success', message: t('settings.saveData.automaticSaved') })
  }

  const handleRevealHistory = async () => {
    const result = await window.electronAPI?.revealHistoryData()
    if (!result?.success) {
      showToast({ type: 'error', message: result?.error || t('settings.saveData.revealError') })
    }
  }

  const handleBackupHistory = async () => {
    if (!window.electronAPI?.backupHistory) return
    setHistoryBackupRunning(true)
    try {
      const result = await window.electronAPI.backupHistory()
      if (result === null) return
      if (!result.ok) {
        showToast({ type: 'error', message: result.error, duration: 6000 })
        return
      }
      showToast({ type: 'success', message: t('settings.saveData.backupSuccess') })
    } finally {
      setHistoryBackupRunning(false)
    }
  }

  const handleSavePlayerName = async () => {
    const success = await saveSettings({ playerName })
    if (success) {
      showToast({ type: 'success', message: t('settings.saveData.playerNameSaved') })
    }
  }

  const handleConnectDiscord = async () => { await connectDiscord() }
  const handleDisconnectDiscord = async () => { await disconnectDiscord() }

  const handleUpdateChannelChange = async (rawValue: string) => {
    const nextChannel = normalizeUpdateChannel(rawValue)
    if (nextChannel === updateChannel) return

    const previousChannel = updateChannel
    setUpdateChannel(nextChannel)
    setUpdateChannelSaving(true)
    markPreferenceSaved('updateChannel', false)
    const success = await saveSettings({ updateChannel: nextChannel })
    setUpdateChannelSaving(false)

    if (!success) {
      setUpdateChannel(previousChannel)
      showToast({
        type: 'error',
        message: t('settings.updateChannel.toastError'),
        duration: 4000,
      })
      return
    }

    markPreferenceSaved('updateChannel', true)
  }

  const [retrying, setRetrying] = useState(false)
  const handleUiScaleChange = async (rawValue: string) => {
    const nextScale = Number(rawValue)
    if (!Number.isFinite(nextScale)) return
    if (Math.abs(nextScale - uiScale) < 0.0001) return

    const previousScale = uiScale
    setUiScale(nextScale)
    setUiScaleSaving(true)
    markPreferenceSaved('uiScale', false)

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

    markPreferenceSaved('uiScale', true)
  }

  const handleUiThemeChange = async (rawValue: string) => {
    const nextTheme = normalizeUiTheme(rawValue)
    if (nextTheme === uiTheme) return

    const previousTheme = uiTheme
    setUiTheme(nextTheme)
    onThemeChange?.(nextTheme)
    setUiThemeSaving(true)
    markPreferenceSaved('uiTheme', false)

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

    markPreferenceSaved('uiTheme', true)
  }

  const handleChronicleRefreshModeChange = async (rawValue: string) => {
    const nextMode = normalizeChronicleRefreshMode(rawValue)
    if (nextMode === chronicleRefreshMode) return

    const previousMode = chronicleRefreshMode
    setChronicleRefreshMode(nextMode)
    onChronicleRefreshModeChange?.(nextMode)
    setChronicleRefreshModeSaving(true)
    markPreferenceSaved('chronicleRefreshMode', false)

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

    markPreferenceSaved('chronicleRefreshMode', true)
  }

  const handleModelRoutingModeChange = async (rawValue: string) => {
    const nextMode = normalizeModelRoutingMode(rawValue)
    if (nextMode === modelRoutingMode) return

    const previousMode = modelRoutingMode
    setModelRoutingMode(nextMode)
    onModelRoutingModeChange?.(nextMode)
    setModelRoutingModeSaving(true)
    markPreferenceSaved('modelRoutingMode', false)

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

    markPreferenceSaved('modelRoutingMode', true)
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
    markPreferenceSaved('language', false)

    const success = await onLanguageSelect?.(nextLanguage) ?? false
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

    markPreferenceSaved('language', true)
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
    label: option.value === 'system' ? t('languages.system') : option.nativeLabel,
  }))

  const geminiQuotaMode = routingModeToQuotaMode(modelRoutingMode)
  const geminiQuotaLabel = (mode: GeminiQuotaMode) => t(`settings.geminiQuota.${mode}`)
  const geminiQuotaTag = (mode: GeminiQuotaMode) => t(`settings.geminiQuota.${mode}Tag`)
  const geminiQuotaHelper = (mode: GeminiQuotaMode) => t(`settings.geminiQuota.${mode}Help`)
  const updateChannelLabel = (channel: UpdateChannel) =>
    t(`settings.updateChannel.${channel}`)
  const hasPlayerNameChange = Boolean(settings && playerName !== (settings.playerName || ''))

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
    <div className="settings-scroll h-full overflow-y-auto custom-scrollbar pr-2 pb-10">
      <div className="max-w-4xl mx-auto pt-2">
        
        {/* Header Area */}
        <header className="settings-header mb-8 space-y-6">
          <div className="settings-heading-row flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
                <HUDMicro className="mb-1 text-accent-cyan">{t('settings.eyebrow')}</HUDMicro>
                <HUDHeader size="xl" className="leading-tight break-words text-glow-sm">{t('settings.title')}</HUDHeader>
            </div>
            <nav aria-label={t('visualQuality.settingsSections')} className="settings-sections w-52 max-w-full min-w-0">
              <HUDSelect
                label={t('visualQuality.settingsSections')}
                value=""
                onChange={event => revealSettingsSection(event.target.value)}
                options={[
                  { value: '', label: t('visualQuality.jumpToSection') },
                  ...[['ai-setup', 'intelligence'], ['save-data', 'data'], ['communications', 'communications'], ['updates', 'updates'], ['diagnostics', 'diagnostics']].map(([value, label]) => ({ value, label: t(`settings.sections.${label}`) })),
                ]}
              />
            </nav>
          </div>
            <div className="settings-preferences grid grid-cols-1 gap-x-5 gap-y-4">
              <div>
                <HUDSelect
                  label={t('settings.textSize')}
                  value={String(uiScale)}
                  disabled={uiScaleSaving}
                  onChange={(e) => void handleUiScaleChange(e.target.value)}
                  options={UI_SCALE_OPTIONS}
                />
                <div className="mt-1"><PreferenceFeedback saving={uiScaleSaving} saved={savedPreferences.uiScale} hint="CMD/CTRL +/-/0" /></div>
              </div>
              <div>
                <HUDSelect
                  label={t('settings.colorTheme')}
                  value={uiTheme}
                  disabled={uiThemeSaving}
                  onChange={(e) => void handleUiThemeChange(e.target.value)}
                  options={UI_THEME_OPTIONS}
                />
                <div className="mt-1"><PreferenceFeedback saving={uiThemeSaving} saved={savedPreferences.uiTheme} hint={t('settings.themePreset')} /></div>
              </div>
              <div>
                <HUDSelect
                  label={t('settings.language')}
                  value={language}
                  disabled={languageSaving}
                  onChange={(e) => void handleLanguageChange(e.target.value)}
                  options={languageOptions}
                />
                <div className="mt-1"><PreferenceFeedback saving={languageSaving} saved={savedPreferences.language} hint={t('settings.languageHint')} /></div>
              </div>
            </div>
            <p className="text-xs text-text-secondary">{t('visualQuality.settingsSaveHelp')}</p>
        </header>

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
        
        {/* Main Grid Layout */}
        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
            
            {/* Column 1: Core Systems */}
            <div className={`space-y-8 ${aiRoute === 'relay' ? 'md:col-span-2' : ''}`}>
                
                <section id="ai-setup" tabIndex={-1}>
                  <HUDSectionTitle number="01">{t('settings.sections.intelligence')}</HUDSectionTitle>
                  <HUDPanel decoration="tech" title={t('settings.aiSetup.chooseRoute')} quiet>
                    <div className="space-y-4 pt-2">
                      <AISetupChoice value={aiRoute} onChange={route => {
                        setAIRoute(route)
                        requestAnimationFrame(() => revealSettingsSection(route === 'relay' ? 'ai-app-connections' : 'ai-setup'))
                      }} />
                      {aiRoute === 'relay' ? <MCPRelayPanel active={isActive} onChooseCampaign={handleBrowse} /> : <>
                      {(settings?.secretStorageReadFailed || settings?.secretStorageAvailable === false) && (
                        <HUDMicro className="block text-accent-yellow">{t(settings.secretStorageReadFailed ? (advisorProvider === 'chatgpt' ? 'chatgpt.lockedSecrets' : 'settings.advisor.lockedSecrets') : (advisorProvider === 'chatgpt' ? 'chatgpt.sessionOnly' : 'settings.advisor.sessionOnlySecrets'))}</HUDMicro>
                      )}
                      <AISetupForm
                        initialSettings={settings}
                        onSave={saveSettings}
                        onProviderChange={setAdvisorProvider}
                        onChatGPTActivated={reload}
                      />
                      {advisorProvider === 'gemini' && <div className="space-y-3 border-t border-white/10 pt-4">
                        <div className="flex items-center justify-between gap-3">
                          <HUDLabel>{t('settings.geminiQuota.label')}</HUDLabel>
                          <PreferenceFeedback saving={modelRoutingModeSaving} saved={savedPreferences.modelRoutingMode} />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {GEMINI_QUOTA_MODES.map(mode => <button key={mode} type="button" disabled={modelRoutingModeSaving} aria-pressed={geminiQuotaMode === mode} aria-label={t('settings.geminiQuota.aria', { mode: geminiQuotaLabel(mode) })} onClick={() => void handleGeminiQuotaModeChange(mode)} className={`rounded border p-3 text-left ${geminiQuotaMode === mode ? 'border-accent-cyan text-accent-cyan' : 'border-white/20 text-text-secondary'}`}>
                            <span className="block text-sm">{geminiQuotaLabel(mode)}</span>
                            <span className="mt-1 block text-xs">{geminiQuotaTag(mode)}</span>
                          </button>)}
                        </div>
                        <p className="text-xs text-text-secondary">{geminiQuotaHelper(geminiQuotaMode)}</p>
                      </div>}
                      <ChronicleRefreshControl mode={chronicleRefreshMode} saving={chronicleRefreshModeSaving} saved={savedPreferences.chronicleRefreshMode} onChange={mode => void handleChronicleRefreshModeChange(mode)} />
                      </>}
                    </div>
                  </HUDPanel>
                </section>
            </div>

            {/* Column 2: Game and campaign essentials */}
            <div className="space-y-8">

                {/* Save Data Section */}
                <section id="save-data" tabIndex={-1}>
                    <HUDSectionTitle number="02">{t('settings.sections.data')}</HUDSectionTitle>
                    <div className="space-y-4">
                      <HUDPanel decoration="brackets" title={t('settings.panels.saveSource')} quiet>
                        <div className="space-y-4 pt-2">
                          <HUDInput
                            label={t('settings.saveData.directoryLabel')}
                            value={saveDir}
                            onChange={(e) => setSaveDir(e.target.value)}
                            placeholder={t('settings.saveData.placeholder')}
                            readOnly
                          />
                          <div className="flex flex-wrap gap-2">
                            <HUDButton
                              type="button"
                              variant="secondary"
                              onClick={handleBrowse}
                              className="px-3 py-1.5 text-[10px]"
                            >
                              {t('settings.saveData.changeFolder')}
                            </HUDButton>
                            {saveDir && (
                              <HUDButton
                                type="button"
                                variant="ghost"
                                onClick={() => void handleUseAutomaticSaveFolder()}
                                className="px-3 py-1.5 text-[10px]"
                              >
                                {t('settings.saveData.useAutomatic')}
                              </HUDButton>
                            )}
                          </div>
                          <HUDMicro className="block normal-case tracking-[0.02em] text-white/45">
                            {t('settings.saveData.target')}
                          </HUDMicro>

                          <div className="border-t border-white/10 pt-4">
                            <button
                              type="button"
                              aria-expanded={multiplayerOpen}
                              onClick={() => setMultiplayerOpen(open => !open)}
                              className="flex w-full items-center justify-between gap-3 text-left"
                            >
                              <HUDLabel>{t('settings.saveData.multiplayerSettings')}</HUDLabel>
                              <span
                                aria-hidden="true"
                                className={`text-xs text-text-secondary transition-transform ${multiplayerOpen ? 'rotate-90' : ''}`}
                              >
                                ›
                              </span>
                            </button>
                            {multiplayerOpen && (
                              <div className="mt-4">
                                <HUDInput
                                  label={t('settings.saveData.playerNameLabel')}
                                  value={playerName}
                                  onChange={(e) => setPlayerName(e.target.value)}
                                  placeholder={t('settings.saveData.playerNamePlaceholder')}
                                />
                                <HUDMicro className="mt-2 block normal-case tracking-[0.02em] text-white/45">
                                  {t('settings.saveData.playerNameHelp')}
                                </HUDMicro>
                                <div className="mt-3 flex justify-end">
                                  <HUDButton
                                    type="button"
                                    variant="secondary"
                                    onClick={() => void handleSavePlayerName()}
                                    disabled={saving || !hasPlayerNameChange}
                                    className="px-3 py-1.5 text-[10px]"
                                  >
                                    {saving ? t('common.applying') : t('settings.saveData.savePlayerName')}
                                  </HUDButton>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </HUDPanel>

                      <HUDPanel decoration="brackets" title={t('settings.panels.campaignHistory')} quiet>
                        <div className="space-y-4 pt-2">
                          <div>
                            <p className="font-mono text-sm text-text-primary">
                              {historyStorage
                                ? t('settings.saveData.historySize', { size: formatBytes(historyStorage.bytes) })
                                : t('settings.saveData.historyLoading')}
                            </p>
                            <p className="mt-2 text-xs leading-relaxed text-text-secondary">
                              {t('settings.saveData.historyHelp')}
                            </p>
                          </div>
                          <div className="grid max-w-lg grid-cols-1 gap-2 xl:grid-cols-2">
                            <HUDButton
                              type="button"
                              onClick={onOpenCampaignHistory}
                              aria-label={t('settings.saveData.manageCampaignsAria')}
                              className="w-full px-3 py-1.5 text-[10px] xl:col-span-2"
                            >
                              {t('chronicle.sidebar.manageCampaigns')}
                            </HUDButton>
                            <HUDButton
                              type="button"
                              variant="secondary"
                              onClick={() => void handleBackupHistory()}
                              disabled={historyBackupRunning}
                              className="w-full px-3 py-1.5 text-[10px]"
                            >
                              {historyBackupRunning ? t('settings.saveData.backingUp') : t('settings.saveData.backupHistory')}
                            </HUDButton>
                            <HUDButton
                              type="button"
                              variant="ghost"
                              onClick={() => void handleRevealHistory()}
                              className="w-full px-3 py-1.5 text-[10px]"
                              title={historyStorage?.path}
                            >
                              {t('settings.saveData.revealHistory')}
                            </HUDButton>
                          </div>
                        </div>
                      </HUDPanel>
                    </div>
                </section>

            </div>

        </div>

        <details className="group mt-8 rounded-sm border border-white/10 bg-black/15">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4 transition-colors hover:bg-white/5">
            <span>
              <span className="block font-display text-sm uppercase tracking-[0.16em] text-text-primary">
                {t('settings.moreSettings.title')}
              </span>
              <HUDMicro className="mt-1 block normal-case tracking-[0.02em] text-white/45">
                {t('settings.moreSettings.help')}
              </HUDMicro>
            </span>
            <span className="flex items-center gap-3">
              <HUDMicro>{t('settings.moreSettings.optional')}</HUDMicro>
              <span aria-hidden="true" className="text-accent-cyan transition-transform group-open:rotate-90">›</span>
            </span>
          </summary>
          <div className="grid grid-cols-1 gap-8 border-t border-white/10 p-4 md:grid-cols-2 md:p-6">
            {/* Optional connections */}
            <div className="space-y-8">
                {/* Discord Section */}
                <section id="communications" tabIndex={-1}>
                    <HUDSectionTitle number="04">{t('settings.sections.communications')}</HUDSectionTitle>
                    <HUDPanel decoration="scanline" variant={discordStatus?.connected ? 'primary' : 'secondary'} title={t('settings.panels.discordLink')} quiet>
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

            </div>

            {/* Updates and support */}
            <div className="space-y-8">

                {/* Software Updates Section */}
                <section id="updates" tabIndex={-1}>
                    <HUDSectionTitle number="05">{t('settings.sections.updates')}</HUDSectionTitle>
                    <HUDPanel decoration="brackets" title={t('settings.panels.updateChannel')} quiet>
                        <div className="space-y-3 pt-2">
                            <div className="flex items-center justify-between gap-3">
                                <HUDLabel>{t('settings.updateChannel.label')}</HUDLabel>
                                <PreferenceFeedback saving={updateChannelSaving} saved={savedPreferences.updateChannel} />
                            </div>
                            <div
                              className="grid grid-cols-2 gap-2 rounded-sm border border-white/10 bg-black/20 p-1"
                              data-testid="update-channel-control"
                            >
                              {(['stable', 'beta'] as const).map((channel) => {
                                const isSelected = updateChannel === channel
                                return (
                                  <button
                                    key={channel}
                                    type="button"
                                    disabled={updateChannelSaving}
                                    aria-pressed={isSelected}
                                    aria-label={t('settings.updateChannel.aria', {
                                      channel: updateChannelLabel(channel),
                                    })}
                                    onClick={() => void handleUpdateChannelChange(channel)}
                                    className={`rounded-sm border px-3 py-2 text-left transition-all duration-200 ${
                                      isSelected
                                        ? 'border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan'
                                        : 'border-transparent bg-transparent text-text-secondary hover:border-white/15 hover:bg-white/5 hover:text-text-primary'
                                    } disabled:cursor-not-allowed disabled:opacity-50`}
                                  >
                                    <div className="font-display text-[11px] uppercase tracking-[0.18em]">
                                      {updateChannelLabel(channel)}
                                    </div>
                                    <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-white/35">
                                      {t(`settings.updateChannel.${channel}Tag`)}
                                    </div>
                                  </button>
                                )
                              })}
                            </div>
                            <HUDMicro className="block text-[10px] leading-relaxed text-white/45 normal-case tracking-[0.02em]">
                              {t(`settings.updateChannel.${updateChannel}Help`)}
                            </HUDMicro>
                            {updateChannel === 'beta' && (
                              <p className="border-l-2 border-accent-yellow/70 pl-3 font-mono text-[10px] leading-relaxed text-accent-yellow/80">
                                {t('settings.updateChannel.betaWarning')}
                              </p>
                            )}
                        </div>
                    </HUDPanel>
                </section>

                {/* Feedback Section */}
                <section id="diagnostics" tabIndex={-1}>
                    <HUDSectionTitle number="06">{t('settings.sections.diagnostics')}</HUDSectionTitle>
                    <div className="flex gap-4 items-center p-4 border border-white/5 bg-black/15 rounded-sm">
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
        </details>

      </div>
    </div>
  )
}

export default SettingsPage
