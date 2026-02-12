import { useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { HUDButton } from './hud/HUDButton'
import { HUDInput } from './hud/HUDInput'
import { HUDMicro } from './hud/HUDText'

interface OnboardingModalProps {
  onComplete: () => void
}

type Step = 1 | 2 | 3

interface SaveDetectionResult {
  found: boolean
  directory: string | null
  saveCount: number
  latest: { name: string; modified: string } | null
}

const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 80 : -80,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? -80 : 80,
    opacity: 0,
  }),
}

const slideTransition = {
  duration: 0.3,
  ease: [0.25, 0.46, 0.45, 0.94] as const,
}

export default function OnboardingModal({ onComplete }: OnboardingModalProps) {
  const [step, setStep] = useState<Step>(1)
  const [direction, setDirection] = useState(1)
  const autoRescanAttemptedRef = useRef(false)
  const autoRescanTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Step 2 state
  const [apiKey, setApiKey] = useState('')

  // Step 3 state
  const [saveResult, setSaveResult] = useState<SaveDetectionResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  const goTo = useCallback((next: Step) => {
    setDirection(next > step ? 1 : -1)
    setStep(next)
  }, [step])

  const clearAutoRescanTimer = useCallback(() => {
    if (autoRescanTimerRef.current) {
      clearTimeout(autoRescanTimerRef.current)
      autoRescanTimerRef.current = null
    }
  }, [])

  // Auto-detect saves when entering step 3
  useEffect(() => {
    if (step === 3) {
      autoRescanAttemptedRef.current = false
      detectSaves()
      return
    }
    clearAutoRescanTimer()
  }, [step, clearAutoRescanTimer])

  useEffect(() => {
    if (step !== 3 || scanning || !saveResult || saveResult.found) return
    if (autoRescanAttemptedRef.current) return

    autoRescanAttemptedRef.current = true
    autoRescanTimerRef.current = setTimeout(() => {
      autoRescanTimerRef.current = null
      void detectSaves(selectedPath || undefined)
    }, 2000)
  }, [step, scanning, saveResult, selectedPath])

  useEffect(() => {
    return () => clearAutoRescanTimer()
  }, [clearAutoRescanTimer])

  async function detectSaves(targetDirectory?: string) {
    clearAutoRescanTimer()
    setScanning(true)
    try {
      const result = targetDirectory
        ? await window.electronAPI?.onboarding.detectSavesInDir(targetDirectory)
        : await window.electronAPI?.onboarding.detectSaves()
      if (result) {
        setSaveResult(result)
        if (result.directory) {
          setSelectedPath(result.directory)
        }
      }
    } catch {
      setSaveResult({
        found: false,
        directory: targetDirectory || null,
        saveCount: 0,
        latest: null,
      })
    } finally {
      setScanning(false)
    }
  }

  async function handleBrowse() {
    const folder = await window.electronAPI?.showFolderDialog()
    if (folder) {
      setSelectedPath(folder)
      await detectSaves(folder)
    }
  }

  async function handleRescan() {
    await detectSaves(selectedPath || undefined)
  }

  async function handleComplete() {
    // Save settings (triggers backend start via restartPythonBackend)
    await window.electronAPI?.saveSettings({
      googleApiKey: apiKey,
      saveDir: selectedPath || '',
    })

    // Mark onboarding complete
    await window.electronAPI?.onboarding.complete()

    onComplete()
  }

  function shortenPath(p: string): string {
    const home = p.match(/^(\/Users\/[^/]+|\/home\/[^/]+|C:\\Users\\[^\\]+)/)
    if (home) {
      return '~' + p.slice(home[0].length)
    }
    return p
  }

  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.25 }}
        className="relative w-full max-w-lg mx-4 bg-bg-elevated border border-border rounded-sm overflow-hidden"
        style={{ boxShadow: '0 0 60px rgba(0, 212, 255, 0.08), 0 8px 32px rgba(0, 0, 0, 0.6)' }}
      >
        {/* Corner accents */}
        <div className="absolute top-0 left-0 w-4 h-4 border-l-2 border-t-2 border-accent-cyan/60 z-10" />
        <div className="absolute top-0 right-0 w-4 h-4 border-r-2 border-t-2 border-accent-cyan/60 z-10" />
        <div className="absolute bottom-0 left-0 w-4 h-4 border-l-2 border-b-2 border-accent-cyan/60 z-10" />
        <div className="absolute bottom-0 right-0 w-4 h-4 border-r-2 border-b-2 border-accent-cyan/60 z-10" />

        {/* Content area with overflow hidden for slide transitions */}
        <div className="relative min-h-[320px]">
          <AnimatePresence mode="wait" custom={direction}>
            {step === 1 && (
              <motion.div
                key="step-1"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={slideTransition}
                className="p-8"
              >
                <StepWelcome onNext={() => goTo(2)} />
              </motion.div>
            )}
            {step === 2 && (
              <motion.div
                key="step-2"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={slideTransition}
                className="p-8"
              >
                <StepApiKey
                  apiKey={apiKey}
                  onChange={setApiKey}
                  onBack={() => goTo(1)}
                  onNext={() => goTo(3)}
                />
              </motion.div>
            )}
            {step === 3 && (
              <motion.div
                key="step-3"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={slideTransition}
                className="p-8"
              >
                <StepSaveDirectory
                  scanning={scanning}
                  saveResult={saveResult}
                  selectedPath={selectedPath}
                  shortenPath={shortenPath}
                  onBrowse={handleBrowse}
                  onRetry={handleRescan}
                  onBack={() => goTo(2)}
                  onComplete={handleComplete}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </motion.div>,
    document.body
  )
}

// =============================================================================
// Step 1: Welcome
// =============================================================================

function StepWelcome({ onNext }: { onNext: () => void }) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-8">
        <h2 className="font-display text-sm tracking-widest text-accent-cyan uppercase">
          First Contact Protocol
        </h2>
        <HUDMicro>01 / 03</HUDMicro>
      </div>

      {/* Body */}
      <div className="flex-1 space-y-4 mb-8">
        <p className="text-sm text-text-primary leading-relaxed">
          Advisor online. Awaiting configuration before strategic operations can commence.
        </p>
      </div>

      {/* Actions */}
      <div className="flex justify-end">
        <HUDButton onClick={onNext}>
          Initialize
        </HUDButton>
      </div>
    </div>
  )
}

// =============================================================================
// Step 2: API Key
// =============================================================================

function StepApiKey({
  apiKey,
  onChange,
  onBack,
  onNext,
}: {
  apiKey: string
  onChange: (v: string) => void
  onBack: () => void
  onNext: () => void
}) {
  const hasKey = apiKey.trim().length > 0

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-8">
        <h2 className="font-display text-sm tracking-widest text-accent-cyan uppercase">
          Intelligence Uplink
        </h2>
        <HUDMicro>02 / 03</HUDMicro>
      </div>

      {/* Body */}
      <div className="flex-1 space-y-5 mb-8">
        <p className="text-sm text-text-secondary leading-relaxed">
          Your advisor runs on Google Gemini. You'll need an API key —
          it's free and takes about 30 seconds.
        </p>

        {/* API Key input box */}
        <div className="relative">
          <HUDInput
            label="API Key Token"
            type="password"
            placeholder="AIza..."
            value={apiKey}
            onChange={(e) => onChange(e.target.value)}
            autoFocus
          />
          {/* Status indicator */}
          <div className="flex justify-end mt-2">
            <span className={`font-mono text-[10px] tracking-widest uppercase ${hasKey ? 'text-accent-green' : 'text-accent-red'}`}>
              STATUS: {hasKey ? 'READY' : 'MISSING'}
            </span>
          </div>
        </div>

        {/* External link */}
        <a
          href="https://aistudio.google.com/apikey"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-xs text-accent-cyan hover:text-accent-cyan/80 transition-colors"
        >
          Generate key at Google AI Studio &rarr;
        </a>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3">
        <HUDButton variant="secondary" onClick={onBack}>
          Back
        </HUDButton>
        <HUDButton onClick={onNext} disabled={!hasKey}>
          Next
        </HUDButton>
      </div>
    </div>
  )
}

// =============================================================================
// Step 3: Save Directory
// =============================================================================

function StepSaveDirectory({
  scanning,
  saveResult,
  selectedPath,
  shortenPath,
  onBrowse,
  onRetry,
  onBack,
  onComplete,
}: {
  scanning: boolean
  saveResult: SaveDetectionResult | null
  selectedPath: string | null
  shortenPath: (p: string) => string
  onBrowse: () => void
  onRetry: () => void
  onBack: () => void
  onComplete: () => void
}) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-8">
        <h2 className="font-display text-sm tracking-widest text-accent-cyan uppercase">
          Data Link
        </h2>
        <HUDMicro>03 / 03</HUDMicro>
      </div>

      {/* Body */}
      <div className="flex-1 mb-8">
        {scanning ? (
          <SaveScanning />
        ) : saveResult?.found ? (
          <SaveFound
            result={saveResult}
            selectedPath={selectedPath}
            shortenPath={shortenPath}
          />
        ) : (
          <SaveNotFound
            selectedPath={selectedPath}
            shortenPath={shortenPath}
          />
        )}
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3">
        <HUDButton variant="secondary" onClick={onBack}>
          Back
        </HUDButton>
        {scanning ? null : saveResult?.found ? (
          <>
            <HUDButton variant="secondary" onClick={onBrowse}>
              Browse Elsewhere
            </HUDButton>
            <HUDButton onClick={onComplete}>
              Confirm
            </HUDButton>
          </>
        ) : (
          <>
            <HUDButton variant="secondary" onClick={onComplete}>
              Set Up Later
            </HUDButton>
            <HUDButton variant="secondary" onClick={onRetry}>
              Scan Again
            </HUDButton>
            <HUDButton onClick={onBrowse}>
              Browse Folder
            </HUDButton>
          </>
        )}
      </div>
    </div>
  )
}

function SaveScanning() {
  return (
    <div className="flex items-center gap-3 py-8">
      <div className="w-3 h-3 border border-accent-cyan border-t-transparent rounded-full animate-spin" />
      <span className="text-sm text-text-secondary">Scanning for save files...</span>
    </div>
  )
}

function SaveFound({
  result,
  selectedPath,
  shortenPath,
}: {
  result: SaveDetectionResult
  selectedPath: string | null
  shortenPath: (p: string) => string
}) {
  const displayPath = selectedPath || result.directory
  return (
    <div className="space-y-4">
      <p className="text-sm text-text-primary">Found your saves.</p>
      <div className="p-4 bg-black/20 border border-white/10 rounded-sm">
        <div className="font-mono text-xs text-accent-cyan mb-1">
          {displayPath ? shortenPath(displayPath) : ''}
        </div>
        <div className="text-xs text-text-secondary">
          {result.saveCount} save file{result.saveCount !== 1 ? 's' : ''} detected
        </div>
      </div>
    </div>
  )
}

function SaveNotFound({
  selectedPath,
  shortenPath,
}: {
  selectedPath: string | null
  shortenPath: (p: string) => string
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-text-primary leading-relaxed">
        We couldn't find your Stellaris saves automatically.
      </p>
      <p className="text-sm text-text-secondary leading-relaxed">
        {selectedPath
          ? `No .sav files were found in ${shortenPath(selectedPath)}.`
          : 'We checked the default save locations but did not find any .sav files yet.'}
      </p>
      <p className="text-sm text-text-secondary leading-relaxed">
        Click Browse Folder and select your "Stellaris/save games" folder, or choose Set Up Later and configure it in Settings.
      </p>
    </div>
  )
}
