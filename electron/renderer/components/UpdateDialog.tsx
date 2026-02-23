import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface UpdateState {
  available: boolean
  version?: string
  checking: boolean
  downloading: boolean
  installing: boolean
  progress: number
  error?: string
}

export default function UpdateDialog() {
  const [update, setUpdate] = useState<UpdateState>({
    available: false,
    checking: false,
    downloading: false,
    installing: false,
    progress: 0,
  })

  // Check for updates on mount
  useEffect(() => {
    const checkUpdates = async () => {
      setUpdate(prev => ({ ...prev, checking: true }))
      try {
        const result = await (window as any).electronAPI.checkForUpdate()
        if (result?.updateAvailable) {
          setUpdate(prev => ({
            ...prev,
            available: true,
            version: result.version,
          }))
        }
      } catch (err) {
        console.error('Failed to check for updates:', err)
      } finally {
        setUpdate(prev => ({ ...prev, checking: false }))
      }
    }

    checkUpdates()
  }, [])

  // Listen for update events
  useEffect(() => {
    const unlistenUpdateAvailable = (window as any).electronAPI.onUpdateAvailable((info: { version?: string }) => {
      setUpdate(prev => ({
        ...prev,
        available: true,
        version: info?.version ?? prev.version,
        error: undefined,
      }))
    })

    const unlistenDownloadProgress = (window as any).electronAPI.onUpdateDownloadProgress((progress: number) => {
      setUpdate(prev => ({
        ...prev,
        available: true,
        downloading: true,
        progress,
        error: undefined,
      }))
    })

    const unlistenUpdateDownloaded = (window as any).electronAPI.onUpdateDownloaded((info: { version?: string }) => {
      setUpdate(prev => ({
        ...prev,
        available: true,
        version: info?.version ?? prev.version,
        downloading: false,
        installing: false,
        progress: 100,
      }))
    })

    const unlistenUpdateInstalling = (window as any).electronAPI.onUpdateInstalling(() => {
      setUpdate(prev => ({
        ...prev,
        available: true,
        installing: true,
        downloading: false,
        error: undefined,
      }))
    })

    const unlistenUpdateError = (window as any).electronAPI.onUpdateError((error: string) => {
      setUpdate(prev => ({
        ...prev,
        installing: false,
        downloading: false,
        error,
      }))
    })

    return () => {
      unlistenUpdateAvailable?.()
      unlistenDownloadProgress?.()
      unlistenUpdateDownloaded?.()
      unlistenUpdateInstalling?.()
      unlistenUpdateError?.()
    }
  }, [])

  const handleInstall = async () => {
    setUpdate(prev => ({
      ...prev,
      installing: true,
      error: undefined,
    }))

    try {
      const result = await (window as any).electronAPI.installUpdate()
      if (!result?.success) {
        setUpdate(prev => ({
          ...prev,
          installing: false,
          error: result?.error || 'Failed to install update',
        }))
      }
    } catch (err) {
      console.error('Failed to install update:', err)
      setUpdate(prev => ({
        ...prev,
        installing: false,
        error: 'Failed to install update',
      }))
    }
  }

  const handleDismiss = () => {
    if (update.installing) return

    setUpdate(prev => ({
      ...prev,
      available: false,
      error: undefined,
    }))
  }

  if (!update.available) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9998] flex items-center justify-center"
        onClick={() => {
          if (!update.installing) handleDismiss()
        }}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="relative w-full max-w-md p-8 bg-bg-secondary border border-border rounded-lg shadow-panel-cyan-update"
          onClick={e => e.stopPropagation()}
        >
          {/* Corner accents */}
          <div className="absolute top-0 left-0 w-3 h-3 border-l-2 border-t-2 border-accent-cyan/50" />
          <div className="absolute top-0 right-0 w-3 h-3 border-r-2 border-t-2 border-accent-cyan/50" />
          <div className="absolute bottom-0 left-0 w-3 h-3 border-l-2 border-b-2 border-accent-cyan/50" />
          <div className="absolute bottom-0 right-0 w-3 h-3 border-r-2 border-b-2 border-accent-cyan/50" />

          {/* Glow effect */}
          <div className="absolute inset-0 rounded-lg pointer-events-none shadow-inset-cyan" />

          <div className="relative z-10">
            {/* Header */}
            <div className="mb-6">
              <h2 className="text-xl font-bold text-accent-cyan mb-1 tracking-wide">
                Update Available
              </h2>
              <p className="text-text-secondary text-sm">
                Stellaris Companion {update.version}
              </p>
            </div>

            {/* Content */}
            {update.error ? (
              <div className="mb-6 p-4 bg-accent-red/10 border border-accent-red/40 rounded-md">
                <p className="text-accent-red text-sm">{update.error}</p>
              </div>
            ) : (
              <div className="mb-6">
                {update.installing ? (
                  <p className="text-text-primary text-sm mb-4">
                    Applying update and relaunching. This can take a little while on macOS.
                  </p>
                ) : (
                  <p className="text-text-primary text-sm mb-4">
                    A new version is ready to install. Restart the app to apply the update.
                  </p>
                )}

                {/* Progress bar */}
                {update.downloading && (
                  <div className="mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-text-secondary">Downloading</span>
                      <span className="text-xs text-accent-cyan font-semibold">{update.progress}%</span>
                    </div>
                    <div className="w-full h-2 bg-bg-tertiary rounded-full overflow-hidden border border-border/50">
                      <motion.div
                        className="h-full bg-gradient-to-r from-accent-cyan to-accent-teal"
                        style={{
                          boxShadow: '0 0 10px rgb(var(--color-accent-cyan) / 0.6)',
                        }}
                        initial={{ width: 0 }}
                        animate={{ width: `${update.progress}%` }}
                        transition={{ duration: 0.3 }}
                      />
                    </div>
                  </div>
                )}

                {update.progress === 100 && !update.downloading && (
                  <div className="mb-4 p-3 bg-accent-green/10 border border-accent-green/40 rounded-md">
                    <p className="text-accent-green text-xs font-semibold">
                      ✓ Downloaded. Ready to install.
                    </p>
                  </div>
                )}

                {update.installing && (
                  <div className="mb-4 p-3 bg-accent-cyan/10 border border-accent-cyan/40 rounded-md">
                    <p className="text-accent-cyan text-xs font-semibold">
                      Applying update...
                    </p>
                  </div>
                )}

                {update.checking && !update.installing && !update.downloading && (
                  <p className="text-xs text-text-secondary">Checking for updates...</p>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={handleDismiss}
                disabled={update.installing}
                className="flex-1 px-4 py-2.5 bg-bg-tertiary hover:bg-bg-elevated border border-border rounded text-text-primary text-sm font-semibold uppercase tracking-wider transition-colors"
              >
                {update.error ? 'Close' : 'Later'}
              </button>

              {!update.error && (
                <button
                  onClick={handleInstall}
                  disabled={update.installing || (update.downloading && update.progress < 100)}
                  className="flex-1 px-4 py-2.5 bg-gradient-to-r from-accent-cyan/20 to-accent-teal/20 hover:from-accent-cyan/30 hover:to-accent-teal/30 border border-accent-cyan/50 hover:border-accent-cyan rounded text-accent-cyan text-sm font-semibold uppercase tracking-wider transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{
                    boxShadow: '0 0 10px rgb(var(--color-accent-cyan) / 0.2)',
                  }}
                >
                  {update.installing
                    ? 'Applying Update...'
                    : update.downloading
                      ? `Downloading... ${update.progress}%`
                      : 'Install & Restart'}
                </button>
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
