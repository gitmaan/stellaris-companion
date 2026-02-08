import { useState, useEffect, useRef } from 'react'
import { useSettings } from '../hooks/useSettings'
import { useDiscord } from '../hooks/useDiscord'
import { HUDHeader, HUDSectionTitle, HUDMicro, HUDLabel } from '../components/hud/HUDText'
import { HUDPanel } from '../components/hud/HUDPanel'
import { HUDInput } from '../components/hud/HUDInput'
import { HUDButton } from '../components/hud/HUDButton'

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
}

function SettingsPage({ onReportIssue }: SettingsPageProps) {
  const { settings, loading, saving, error, saveSettings, showFolderDialog } = useSettings()

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
    }
  }, [settings])

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
            <div className="hidden md:block text-right">
               <HUDMicro>TERMINAL ID: 8X-229</HUDMicro>
               <HUDMicro>SECURE CONNECTION</HUDMicro>
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
                    <div className="w-2 h-2 bg-accent-green shadow-[0_0_10px_rgba(72,187,120,0.8)]" />
                    <span className="font-mono text-accent-green text-sm">CONFIGURATION SAVED // REBOOTING SUBSYSTEMS...</span>
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
