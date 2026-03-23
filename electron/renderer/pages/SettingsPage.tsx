import { useState, useEffect, useRef, useCallback } from 'react'
import { DEFAULT_UI_THEME, normalizeUiTheme, type UiTheme, useSettings, type LLMProvider, DEFAULT_LLM_PROVIDER, normalizeLLMProvider } from '../hooks/useSettings'
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

const LLM_PROVIDER_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'openai', label: 'OpenAI GPT' },
  { value: 'anthropic', label: 'Anthropic Claude' },
  { value: 'openai-compatible', label: 'OpenAI-Compatible (Local)' },
  { value: 'ollama', label: 'Ollama (Local)' },
]

// Which providers require which API key
const PROVIDER_API_KEY_MAP: Record<LLMProvider, 'google' | 'openai' | 'anthropic' | 'none'> = {
  'gemini': 'google',
  'openai': 'openai',
  'anthropic': 'anthropic',
  'openai-compatible': 'none',
  'ollama': 'none',
}

// Default base URLs for local providers
const DEFAULT_BASE_URLS: Partial<Record<LLMProvider, string>> = {
  'openai-compatible': 'http://localhost:1234/v1',
  'ollama': 'http://localhost:11434',
}

// Providers that require model selection (no sensible default)
const LOCAL_PROVIDERS: LLMProvider[] = ['openai-compatible', 'ollama']

interface OllamaModel {
  name: string
  size: number
  modifiedAt: string
}

function SettingsPage({ onReportIssue, onThemeChange }: SettingsPageProps) {
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
  const [openaiApiKey, setOpenaiApiKey] = useState('')
  const [anthropicApiKey, setAnthropicApiKey] = useState('')
  const [llmProvider, setLlmProvider] = useState<LLMProvider>(DEFAULT_LLM_PROVIDER)
  const [llmModel, setLlmModel] = useState('')
  const [llmBaseUrl, setLlmBaseUrl] = useState('')
  const [saveDir, setSaveDir] = useState('')
  const [uiScale, setUiScale] = useState(1)
  const [uiScaleSaving, setUiScaleSaving] = useState(false)
  const [uiTheme, setUiTheme] = useState<UiTheme>(DEFAULT_UI_THEME)
  const [uiThemeSaving, setUiThemeSaving] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Ollama model fetching state
  const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([])
  const [ollamaModelsLoading, setOllamaModelsLoading] = useState(false)
  const [ollamaModelsError, setOllamaModelsError] = useState<string | null>(null)

  // Check if model is required but missing
  const isLocalProvider = LOCAL_PROVIDERS.includes(llmProvider)
  const modelRequired = isLocalProvider && !llmModel.trim()

  // Fetch Ollama models when provider is ollama and base URL changes
  const fetchOllamaModels = useCallback(async (baseUrl: string) => {
    if (!window.electronAPI?.fetchOllamaModels) return
    
    setOllamaModelsLoading(true)
    setOllamaModelsError(null)
    
    try {
      const result = await window.electronAPI.fetchOllamaModels(baseUrl)
      if (result.error) {
        setOllamaModelsError(result.error)
        setOllamaModels([])
      } else {
        setOllamaModels(result.models)
        // If we got models and no model is selected, auto-select the first one
        if (result.models.length > 0 && !llmModel) {
          setLlmModel(result.models[0].name)
        }
      }
    } catch (err) {
      setOllamaModelsError(err instanceof Error ? err.message : 'Failed to fetch models')
      setOllamaModels([])
    } finally {
      setOllamaModelsLoading(false)
    }
  }, [llmModel])

  // Fetch models when Ollama is selected and base URL is available
  useEffect(() => {
    if (llmProvider === 'ollama' && llmBaseUrl) {
      fetchOllamaModels(llmBaseUrl)
    } else {
      setOllamaModels([])
      setOllamaModelsError(null)
    }
  }, [llmProvider, llmBaseUrl, fetchOllamaModels])

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
      setOpenaiApiKey(settings.openaiApiKeySet ? settings.openaiApiKey : '')
      setAnthropicApiKey(settings.anthropicApiKeySet ? settings.anthropicApiKey : '')
      setLlmProvider(normalizeLLMProvider(settings.llmProvider))
      setLlmModel(settings.llmModel || '')
      setLlmBaseUrl(settings.llmBaseUrl || '')
      setSaveDir(settings.saveDir || '')
      setUiScale(settings.uiScale || 1)
      const normalizedTheme = normalizeUiTheme(settings.uiTheme)
      setUiTheme(normalizedTheme)
      onThemeChange?.(normalizedTheme)
    }
  }, [onThemeChange, settings])

  useEffect(() => {
    if (!settings) return
    
    // Check for API key changes (only if not masked)
    const hasGoogleKeyChange = settings.googleApiKeySet 
      ? googleApiKey !== settings.googleApiKey 
      : googleApiKey !== ''
    const hasOpenaiKeyChange = settings.openaiApiKeySet 
      ? openaiApiKey !== settings.openaiApiKey 
      : openaiApiKey !== ''
    const hasAnthropicKeyChange = settings.anthropicApiKeySet 
      ? anthropicApiKey !== settings.anthropicApiKey 
      : anthropicApiKey !== ''
    
    // Check for LLM provider changes
    const hasProviderChange = llmProvider !== (settings.llmProvider || DEFAULT_LLM_PROVIDER)
    const hasModelChange = llmModel !== (settings.llmModel || '')
    const hasBaseUrlChange = llmBaseUrl !== (settings.llmBaseUrl || '')
    
    // Check for path change
    const hasPathChange = saveDir !== (settings.saveDir || '')
    
    setHasChanges(
      hasGoogleKeyChange || 
      hasOpenaiKeyChange || 
      hasAnthropicKeyChange || 
      hasProviderChange || 
      hasModelChange || 
      hasBaseUrlChange || 
      hasPathChange
    )
  }, [googleApiKey, openaiApiKey, anthropicApiKey, llmProvider, llmModel, llmBaseUrl, saveDir, settings])

  const handleBrowse = async () => {
    const selectedPath = await showFolderDialog()
    if (selectedPath) setSaveDir(selectedPath)
  }

  const handleSave = async () => {
    setSaveSuccess(false)
    const settingsToSave: Record<string, string | boolean> = { 
      saveDir,
      llmProvider,
      llmModel,
      llmBaseUrl,
    }
    
    // Only save API keys if they're not masked (i.e., user entered a new value)
    if (!googleApiKey.includes('...')) {
      settingsToSave.googleApiKey = googleApiKey
    }
    if (!openaiApiKey.includes('...')) {
      settingsToSave.openaiApiKey = openaiApiKey
    }
    if (!anthropicApiKey.includes('...')) {
      settingsToSave.anthropicApiKey = anthropicApiKey
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
                    <HUDPanel decoration="tech" title="LLM PROVIDER CONFIG">
                        <div className="space-y-4 pt-2">
                             {/* Provider Selection */}
                             <HUDSelect
                                label="AI PROVIDER"
                                value={llmProvider}
                                onChange={(e) => {
                                  const newProvider = normalizeLLMProvider(e.target.value)
                                  const oldProvider = llmProvider
                                  setLlmProvider(newProvider)
                                  
                                  // Auto-fill default base URL for local providers
                                  // Update if: switching TO a local provider AND either:
                                  // - base URL is empty, OR
                                  // - base URL matches the OLD provider's default (user didn't customize it)
                                  const isLocalProvider = !!DEFAULT_BASE_URLS[newProvider]
                                  const oldProviderDefault = DEFAULT_BASE_URLS[oldProvider]
                                  const isBaseUrlDefault = !llmBaseUrl || llmBaseUrl === oldProviderDefault
                                  
                                  if (isLocalProvider && isBaseUrlDefault) {
                                    setLlmBaseUrl(DEFAULT_BASE_URLS[newProvider] || '')
                                  } else if (!isLocalProvider) {
                                    // Clear base URL when switching to cloud providers
                                    setLlmBaseUrl('')
                                  }
                                }}
                                options={LLM_PROVIDER_OPTIONS}
                              />
                             
                             {/* API Key for cloud providers */}
                             {PROVIDER_API_KEY_MAP[llmProvider] === 'google' && (
                               <>
                                 <HUDInput 
                                    label="GOOGLE API KEY"
                                    type="password"
                                    value={googleApiKey}
                                    onChange={(e) => setGoogleApiKey(e.target.value)}
                                    placeholder={settings?.googleApiKeySet ? '••••••••••••••••' : 'ENTER KEY'}
                                 />
                                 <div className="flex justify-between items-center">
                                     <span className="font-mono text-xs text-white/30">
                                         STATUS: {settings?.googleApiKeySet ? <span className="text-accent-green">ACTIVE</span> : <span className="text-accent-yellow">REQUIRED</span>}
                                     </span>
                                     <a 
                                        href="https://aistudio.google.com/app/apikey" 
                                        target="_blank" 
                                        rel="noreferrer"
                                        className="font-display text-[10px] text-accent-cyan hover:underline tracking-wider"
                                     >
                                         GET API KEY &gt;
                                     </a>
                                 </div>
                               </>
                             )}
                             
                             {PROVIDER_API_KEY_MAP[llmProvider] === 'openai' && (
                               <>
                                 <HUDInput 
                                    label="OPENAI API KEY"
                                    type="password"
                                    value={openaiApiKey}
                                    onChange={(e) => setOpenaiApiKey(e.target.value)}
                                    placeholder={settings?.openaiApiKeySet ? '••••••••••••••••' : 'ENTER KEY'}
                                 />
                                 <div className="flex justify-between items-center">
                                     <span className="font-mono text-xs text-white/30">
                                         STATUS: {settings?.openaiApiKeySet ? <span className="text-accent-green">ACTIVE</span> : <span className="text-accent-yellow">REQUIRED</span>}
                                     </span>
                                     <a 
                                        href="https://platform.openai.com/api-keys" 
                                        target="_blank" 
                                        rel="noreferrer"
                                        className="font-display text-[10px] text-accent-cyan hover:underline tracking-wider"
                                     >
                                         GET API KEY &gt;
                                     </a>
                                 </div>
                               </>
                             )}
                             
                             {PROVIDER_API_KEY_MAP[llmProvider] === 'anthropic' && (
                               <>
                                 <HUDInput 
                                    label="ANTHROPIC API KEY"
                                    type="password"
                                    value={anthropicApiKey}
                                    onChange={(e) => setAnthropicApiKey(e.target.value)}
                                    placeholder={settings?.anthropicApiKeySet ? '••••••••••••••••' : 'ENTER KEY'}
                                 />
                                 <div className="flex justify-between items-center">
                                     <span className="font-mono text-xs text-white/30">
                                         STATUS: {settings?.anthropicApiKeySet ? <span className="text-accent-green">ACTIVE</span> : <span className="text-accent-yellow">REQUIRED</span>}
                                     </span>
                                     <a 
                                        href="https://console.anthropic.com/settings/keys" 
                                        target="_blank" 
                                        rel="noreferrer"
                                        className="font-display text-[10px] text-accent-cyan hover:underline tracking-wider"
                                     >
                                         GET API KEY &gt;
                                     </a>
                                 </div>
                               </>
                             )}
                             
                             {/* Base URL for local providers */}
                             {(llmProvider === 'openai-compatible' || llmProvider === 'ollama') && (
                               <>
                                 <HUDInput 
                                    label="BASE URL"
                                    type="text"
                                    value={llmBaseUrl}
                                    onChange={(e) => setLlmBaseUrl(e.target.value)}
                                    placeholder={DEFAULT_BASE_URLS[llmProvider] || 'http://localhost:8080'}
                                 />
                                 <HUDMicro className="block">
                                     {llmProvider === 'openai-compatible' 
                                       ? 'COMPATIBLE: LM Studio, vLLM, LocalAI, text-generation-webui'
                                       : 'NATIVE OLLAMA API ENDPOINT'
                                     }
                                 </HUDMicro>
                               </>
                             )}
                             
                             {/* Model Selection - Required for local providers, optional for cloud */}
                             {llmProvider === 'ollama' ? (
                               <>
                                 <div className="flex gap-2 items-end">
                                   <div className="flex-1">
                                     <HUDSelect
                                       label="MODEL (REQUIRED)"
                                       value={llmModel}
                                       onChange={(e) => setLlmModel(e.target.value)}
                                       options={
                                         ollamaModels.length > 0
                                           ? ollamaModels.map(m => ({ value: m.name, label: m.name }))
                                           : [{ value: '', label: ollamaModelsLoading ? 'Loading...' : 'No models found' }]
                                       }
                                       disabled={ollamaModelsLoading || ollamaModels.length === 0}
                                     />
                                   </div>
                                   <HUDButton 
                                     variant="secondary" 
                                     onClick={() => llmBaseUrl && fetchOllamaModels(llmBaseUrl)}
                                     disabled={!llmBaseUrl || ollamaModelsLoading}
                                     className="mb-[1px]"
                                   >
                                     {ollamaModelsLoading ? 'SCANNING...' : 'REFRESH'}
                                   </HUDButton>
                                 </div>
                                 <HUDMicro className={`block ${ollamaModelsError ? 'text-accent-red' : ''}`}>
                                   {ollamaModelsError 
                                     ? `ERROR: ${ollamaModelsError.toUpperCase()}`
                                     : ollamaModels.length > 0 
                                       ? `${ollamaModels.length} MODEL${ollamaModels.length !== 1 ? 'S' : ''} AVAILABLE`
                                       : 'CONNECT TO OLLAMA TO LOAD MODELS'
                                   }
                                 </HUDMicro>
                               </>
                             ) : llmProvider === 'openai-compatible' ? (
                               <>
                                 <HUDInput 
                                    label="MODEL NAME (REQUIRED)"
                                    type="text"
                                    value={llmModel}
                                    onChange={(e) => setLlmModel(e.target.value)}
                                    placeholder="e.g., llama-3-8b, mistral-7b"
                                 />
                                 <HUDMicro className={`block ${modelRequired ? 'text-accent-yellow' : ''}`}>
                                     {modelRequired 
                                       ? 'MODEL NAME REQUIRED FOR LOCAL PROVIDERS'
                                       : 'ENTER THE MODEL NAME AS SHOWN IN YOUR LOCAL SERVER'
                                     }
                                 </HUDMicro>
                               </>
                             ) : (
                               <>
                                 <HUDInput 
                                    label="MODEL OVERRIDE (OPTIONAL)"
                                    type="text"
                                    value={llmModel}
                                    onChange={(e) => setLlmModel(e.target.value)}
                                    placeholder="Leave empty for default"
                                 />
                                 <HUDMicro className="block">
                                     OVERRIDE DEFAULT MODEL SELECTION
                                 </HUDMicro>
                               </>
                             )}
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
                     <div className={`w-2 h-2 rounded-full ${modelRequired ? 'bg-accent-red' : hasChanges ? 'bg-accent-yellow animate-pulse' : 'bg-white/20'}`} />
                     <HUDMicro>{modelRequired ? 'MODEL REQUIRED' : hasChanges ? 'UNSAVED CHANGES' : 'SYSTEM READY'}</HUDMicro>
                 </div>
                 <div className="h-4 w-px bg-white/10" />
                 <HUDButton 
                    variant="primary" 
                    onClick={handleSave} 
                    disabled={saving || !hasChanges || modelRequired}
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
