import { useState, useEffect, useRef } from 'react'
import {
  DEFAULT_CHRONICLE_REFRESH_MODE,
  DEFAULT_MODEL_ROUTING_MODE,
  DEFAULT_UI_THEME,
  normalizeChronicleRefreshMode,
  normalizeModelRoutingMode,
  normalizeUiTheme,
  type ChronicleRefreshMode,
  type ModelRoutingMode,
  type UiTheme,
  useSettings,
} from '../hooks/useSettings'
import { useDiscord } from '../hooks/useDiscord'
import { HUDHeader, HUDSectionTitle, HUDMicro, HUDLabel } from '../components/hud/HUDText'
import { HUDPanel } from '../components/hud/HUDPanel'
import { HUDInput } from '../components/hud/HUDInput'
import { HUDButton } from '../components/hud/HUDButton'
import { HUDSelect } from '../components/hud/HUDForm'
import { useToast } from '../components/Toast'

/**
 * DISC-017: Convert technical error messages to user-friendly messages.
 */
function getUserFriendlyErrorMessage(error: string | null): string | null {
  if (!error) return null
  if (error.toLowerCase().includes('cancel') || error.includes('Authorization timeout')) return 'Authorization cancelled.'
  if (error.includes('expired')) return 'Session expired. Reconnect required.'
  if (error.toLowerCase().includes('auth')) return 'Authorization failed.'
  if (error.includes('connect')) return 'Connection error. Check network.'
  return 'System error. Retry.'
}

interface SettingsPageProps {
  onReportIssue?: () => void
  onThemeChange?: (theme: UiTheme) => void
  onChronicleRefreshModeChange?: (mode: ChronicleRefreshMode) => void
  onModelRoutingModeChange?: (mode: ModelRoutingMode) => void
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

const CHRONICLE_REFRESH_MODE_LABELS: Record<ChronicleRefreshMode, string> = {
  balanced: 'Balanced',
  enhanced: 'Enhanced',
}

const CHRONICLE_REFRESH_MODE_HELPERS: Record<ChronicleRefreshMode, string> = {
  balanced: 'Lower Gemini usage. Best default for free tier and steadier cliffhanger updates.',
  enhanced: 'Faster current-era story updates while viewing Chronicle. Uses more Gemini calls.',
}

const MODEL_ROUTING_MODE_LABELS: Record<ModelRoutingMode, string> = {
  quality_first: 'Quality First',
  conserve: 'Quota Saver',
}

const MODEL_ROUTING_MODE_HELPERS: Record<ModelRoutingMode, string> = {
  quality_first: 'Uses Gemini Flash first for Advisor and Chronicle, then falls back to Gemini 3.1 Flash-Lite Preview.',
  conserve: 'Uses Gemini 3.1 Flash-Lite Preview for Advisor to save Gemini Flash quota for Chronicle writing.',
}

function SettingsPage({
  onReportIssue,
  onThemeChange,
  onChronicleRefreshModeChange,
  onModelRoutingModeChange,
}: SettingsPageProps) {
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
  const [hasChanges, setHasChanges] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
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
      setUiTheme(normalizedTheme)
      setChronicleRefreshMode(normalizedChronicleRefreshMode)
      setModelRoutingMode(normalizedModelRoutingMode)
      onThemeChange?.(normalizedTheme)
      onChronicleRefreshModeChange?.(normalizedChronicleRefreshMode)
      onModelRoutingModeChange?.(normalizedModelRoutingMode)
    }
  }, [onChronicleRefreshModeChange, onModelRoutingModeChange, onThemeChange, settings])

  useEffect(() => {
    if (!settings) return
    const hasApiKeyChange = settings.googleApiKeySet ? googleApiKey !== settings.googleApiKey : googleApiKey !== ''
    const hasPathChange = saveDir !== (settings.saveDir || '')
    setHasChanges(hasApiKeyChange || hasPathChange)
  }, [googleApiKey, saveDir, settings])

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
        message: 'Failed to update text size. Please try again.',
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: `Text size set to ${Math.round(nextScale * 100)}%.`,
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
        message: 'Failed to update color theme. Please try again.',
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: `Theme set to ${UI_THEME_LABELS[nextTheme]}.`,
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
        message: 'Failed to update Chronicle refresh mode. Please try again.',
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: `Chronicle refresh mode set to ${CHRONICLE_REFRESH_MODE_LABELS[nextMode]}.`,
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
        message: 'Failed to update model routing. Please try again.',
        duration: 4000,
      })
      return
    }

    showToast({
      type: 'success',
      message: `Model routing set to ${MODEL_ROUTING_MODE_LABELS[nextMode]}.`,
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

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
           <div className="w-12 h-12 border-t-2 border-l-2 border-accent-cyan rounded-full animate-spin" />
           <HUDMicro className="animate-pulse">INITIALIZING CONFIGURATION...</HUDMicro>
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
                <HUDMicro className="mb-1 text-accent-cyan">SYS // CONFIG_01</HUDMicro>
                <HUDHeader size="xl">CONFIGURATION</HUDHeader>
            </div>
            <div className="w-[420px] max-w-[60%] grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <HUDSelect
                  label="Text Size"
                  value={String(uiScale)}
                  disabled={uiScaleSaving}
                  onChange={(e) => void handleUiScaleChange(e.target.value)}
                  options={UI_SCALE_OPTIONS}
                />
                <HUDMicro className="block mt-1 text-right">
                  {uiScaleSaving ? 'APPLYING...' : 'CMD/CTRL +/-/0'}
                </HUDMicro>
              </div>
              <div>
                <HUDSelect
                  label="Color Theme"
                  value={uiTheme}
                  disabled={uiThemeSaving}
                  onChange={(e) => void handleUiThemeChange(e.target.value)}
                  options={UI_THEME_OPTIONS}
                />
                <HUDMicro className="block mt-1 text-right">
                  {uiThemeSaving ? 'APPLYING...' : 'THEME PRESET'}
                </HUDMicro>
              </div>
            </div>
        </div>

        {/* Top Status Messages */}
        {error && (
            <HUDPanel variant="alert" className="mb-6 flex items-center gap-4" decoration="scanline">
                <span className="text-accent-red text-xl">⚠</span>
                <div>
                    <HUDLabel className="text-accent-red">SYSTEM ALERT</HUDLabel>
                    <p className="text-accent-red/80 font-mono text-sm">{error}</p>
                </div>
            </HUDPanel>
        )}
        
        {saveSuccess && (
            <HUDPanel variant="primary" className="mb-6 border-accent-green/50" decoration="scanline">
                <div className="flex items-center gap-3">
                    <div className="w-2 h-2 bg-accent-green shadow-glow-green" />
                    <span className="font-mono text-accent-green text-sm">CONFIGURATION SAVED // SETTINGS APPLIED</span>
                </div>
            </HUDPanel>
        )}

        {/* Main Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            
            {/* Column 1: Core Systems */}
            <div className="space-y-8">
                
                {/* API Section */}
                <section>
                    <HUDSectionTitle number="01">INTELLIGENCE UPLINK</HUDSectionTitle>
                    <HUDPanel decoration="tech" title="GEMINI MODEL ACCESS">
                        <div className="space-y-4 pt-2">
                             <HUDInput 
                                label="API KEY TOKEN"
                                type="password"
                                value={googleApiKey}
                                onChange={(e) => setGoogleApiKey(e.target.value)}
                                placeholder={settings?.googleApiKeySet ? '••••••••••••••••' : 'ENTER KEY'}
                             />
                             <div className="flex justify-between items-center">
                                 <span className="font-mono text-xs text-white/30">
                                     STATUS: {settings?.googleApiKeySet ? <span className="text-accent-green">ACTIVE</span> : <span className="text-accent-yellow">MISSING</span>}
                                 </span>
                                 <a 
                                    href="https://aistudio.google.com/app/apikey" 
                                    target="_blank" 
                                    rel="noreferrer"
                                    className="font-display text-[10px] text-accent-cyan hover:underline tracking-wider"
                                 >
                                     GENERATE KEY &gt;
                                 </a>
                             </div>
                             <div className="border-t border-white/10 pt-4 space-y-3">
                                 <div className="flex items-center justify-between gap-3">
                                     <HUDLabel>MODEL ROUTING</HUDLabel>
                                     {modelRoutingModeSaving && (
                                       <HUDMicro className="text-right">APPLYING...</HUDMicro>
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
                                         aria-label={`Set model routing to ${MODEL_ROUTING_MODE_LABELS[mode]}`}
                                         onClick={() => void handleModelRoutingModeChange(mode)}
                                         className={`relative rounded-sm px-3 py-2 text-left transition-all duration-200 ${
                                           isSelected
                                             ? 'border border-accent-cyan/60 bg-accent-cyan/12 text-accent-cyan shadow-glow-sm'
                                             : 'border border-transparent bg-transparent text-text-secondary hover:border-white/15 hover:bg-white/5 hover:text-text-primary'
                                         } disabled:opacity-50 disabled:cursor-not-allowed`}
                                       >
                                         <div className="font-display text-[11px] uppercase tracking-[0.18em]">
                                           {MODEL_ROUTING_MODE_LABELS[mode]}
                                         </div>
                                         <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-white/35">
                                           {mode === 'quality_first' ? 'FLASH FIRST' : 'FLASH-LITE ADVISOR'}
                                         </div>
                                       </button>
                                     )
                                   })}
                                 </div>

                                 <HUDMicro className="block leading-relaxed text-white/45 normal-case tracking-[0.08em]">
                                   {MODEL_ROUTING_MODE_HELPERS[modelRoutingMode]}
                                 </HUDMicro>
                             </div>

                             <div className="border-t border-white/10 pt-4 space-y-3">
                                 <div className="flex items-center justify-between gap-3">
                                     <HUDLabel>CHRONICLE REFRESH</HUDLabel>
                                     {chronicleRefreshModeSaving && (
                                       <HUDMicro className="text-right">APPLYING...</HUDMicro>
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
                                         aria-label={`Set refresh mode to ${CHRONICLE_REFRESH_MODE_LABELS[mode]}`}
                                         onClick={() => void handleChronicleRefreshModeChange(mode)}
                                         className={`relative rounded-sm px-3 py-2 text-left transition-all duration-200 ${
                                           isSelected
                                             ? 'border border-accent-cyan/60 bg-accent-cyan/12 text-accent-cyan shadow-glow-sm'
                                             : 'border border-transparent bg-transparent text-text-secondary hover:border-white/15 hover:bg-white/5 hover:text-text-primary'
                                         } disabled:opacity-50 disabled:cursor-not-allowed`}
                                       >
                                         <div className="font-display text-[11px] uppercase tracking-[0.18em]">
                                           {CHRONICLE_REFRESH_MODE_LABELS[mode]}
                                         </div>
                                         <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-white/35">
                                           {mode === 'balanced' ? 'FREE-TIER DEFAULT' : 'MORE RESPONSIVE'}
                                         </div>
                                       </button>
                                     )
                                   })}
                                 </div>

                                 <HUDMicro className="block leading-relaxed text-white/45 normal-case tracking-[0.08em]">
                                   {CHRONICLE_REFRESH_MODE_HELPERS[chronicleRefreshMode]}
                                 </HUDMicro>
                             </div>
                        </div>
                    </HUDPanel>
                </section>

                {/* Save Data Section */}
                <section>
                    <HUDSectionTitle number="02">DATA INGESTION</HUDSectionTitle>
                    <HUDPanel decoration="brackets" title="SAVE FILE SOURCE">
                         <div className="space-y-4 pt-2">
                             <div className="flex gap-2 items-end">
                                 <HUDInput 
                                    className="flex-1"
                                    label="DIRECTORY PATH"
                                    value={saveDir}
                                    onChange={(e) => setSaveDir(e.target.value)}
                                    placeholder="AUTO-DETECT"
                                    readOnly
                                 />
                                 <HUDButton variant="secondary" onClick={handleBrowse} className="mb-[1px]">
                                     BROWSE
                                 </HUDButton>
                             </div>
                             <HUDMicro className="block mt-2">
                                 TARGET: STELLARIS SAVE GAME DIRECTORY (LOCAL)
                             </HUDMicro>
                         </div>
                    </HUDPanel>
                </section>

            </div>

            {/* Column 2: Comms & Feedback */}
            <div className="space-y-8">
                
                {/* Discord Section */}
                <section>
                    <HUDSectionTitle number="03">COMMUNICATIONS RELAY</HUDSectionTitle>
                    <HUDPanel decoration="scanline" variant={discordStatus?.connected ? 'primary' : 'secondary'} title="DISCORD LINK">
                        <div className="space-y-4 pt-2">
                            {discordLoading ? (
                                <div className="flex items-center gap-3 py-4 opacity-50">
                                    <div className="w-4 h-4 border border-accent-cyan border-t-transparent rounded-full animate-spin" />
                                    <HUDMicro>ESTABLISHING HANDSHAKE...</HUDMicro>
                                </div>
                            ) : discordStatus?.connected ? (
                                <>
                                    <div className="flex items-center gap-4 bg-white/5 p-3 rounded-sm border border-white/10">
                                        <div className="w-10 h-10 bg-discord rounded flex items-center justify-center text-white font-display text-lg">
                                            {discordStatus?.username?.charAt(0).toUpperCase()}
                                        </div>
                                        <div>
                                            <div className="font-display text-sm tracking-wide text-white">{discordStatus?.username}</div>
                                            <HUDMicro className="text-accent-green">SIGNAL: STRONG</HUDMicro>
                                        </div>
                                    </div>
                                    
                                    <div className="grid grid-cols-2 gap-3">
                                        <HUDButton 
                                            variant="secondary" 
                                            onClick={() => window.open('https://discord.com/oauth2/authorize?client_id=1460412463282524231&scope=bot+applications.commands&permissions=0', '_blank')}
                                            className="text-[10px]"
                                        >
                                            INVITE BOT
                                        </HUDButton>
                                        <HUDButton variant="danger" onClick={handleDisconnectDiscord} className="text-[10px]">
                                            TERMINATE
                                        </HUDButton>
                                    </div>

                                    {/* Relay Status */}
                                    {discordRelayStatus && (
                                        <div className="flex items-center justify-between border-t border-white/10 pt-3 mt-1">
                                            <span className="font-mono text-[10px] text-white/50">RELAY: {discordRelayStatus.state.toUpperCase()}</span>
                                            {discordRelayStatus.state === 'error' && (
                                                <button onClick={handleRetryConnection} disabled={retrying} className="text-accent-yellow hover:underline text-[10px] font-mono">
                                                    {retrying ? 'RETRYING...' : 'RETRY'}
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </>
                            ) : (
                                <>
                                    <p className="font-mono text-xs text-white/60 leading-relaxed">
                                        Enable subspace communications to query advisor via Discord overlay.
                                    </p>
                                    <HUDButton 
                                        variant="primary" 
                                        onClick={handleConnectDiscord}
                                        disabled={discordConnecting}
                                        className="w-full"
                                    >
                                        {discordConnecting ? 'INITIATING...' : 'CONNECT DISCORD'}
                                    </HUDButton>
                                </>
                            )}
                            
                            {discordError && (
                                <p className="text-accent-red text-xs font-mono border-l-2 border-accent-red pl-2">
                                    ERR: {getUserFriendlyErrorMessage(discordError)}
                                </p>
                            )}
                        </div>
                    </HUDPanel>
                </section>

                {/* Feedback Section */}
                <section>
                    <HUDSectionTitle number="04">DIAGNOSTICS</HUDSectionTitle>
                    <div className="flex gap-4 items-center p-4 border border-white/10 bg-white/5 rounded-sm">
                        <div className="flex-1">
                             <HUDLabel className="block mb-1">SYSTEM REPORTING</HUDLabel>
                             <p className="font-mono text-xs text-white/40">Submit detailed logs for analysis.</p>
                        </div>
                        <HUDButton variant="secondary" onClick={onReportIssue}>
                            REPORT ISSUE
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
                     <HUDMicro>{hasChanges ? 'UNSAVED CHANGES' : 'SYSTEM READY'}</HUDMicro>
                 </div>
                 <div className="h-4 w-px bg-white/10" />
                 <HUDButton 
                    variant="primary" 
                    onClick={handleSave} 
                    disabled={saving || !hasChanges}
                    className="min-w-[140px]"
                 >
                     {saving ? 'COMMITTING...' : 'APPLY CHANGES'}
                 </HUDButton>
             </div>
        </div>

      </div>
    </div>
  )
}

export default SettingsPage
