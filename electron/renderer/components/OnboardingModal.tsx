import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { HUDButton } from './hud/HUDButton'
import { HUDInput } from './hud/HUDInput'
import { HUDLabel, HUDMicro } from './hud/HUDText'
import { HUDPanel } from './hud/HUDPanel'
import appLogo from '../assets/app_logo.svg'

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
  const dialogRef = useRef<HTMLDivElement | null>(null)

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

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    const animationFrame = requestAnimationFrame(() => {
      const focusable = getFocusableElements(dialog)
      if (focusable.length > 0) {
        focusable[0].focus()
      } else {
        dialog.focus()
      }
    })

    const handleTab = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return

      const focusable = getFocusableElements(dialog)
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null

      if (event.shiftKey) {
        if (!active || active === first || !dialog.contains(active)) {
          event.preventDefault()
          last.focus()
        }
      } else if (!active || active === last || !dialog.contains(active)) {
        event.preventDefault()
        first.focus()
      }
    }

    dialog.addEventListener('keydown', handleTab)
    return () => {
      cancelAnimationFrame(animationFrame)
      dialog.removeEventListener('keydown', handleTab)
    }
  }, [step, scanning, saveResult?.found])

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
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-step-title"
        tabIndex={-1}
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.25 }}
        className="relative mx-4 h-[min(27.5rem,calc(100vh-4.5rem))] w-[min(41rem,calc(100%-2rem))] outline-none"
      >
        <div className="relative h-full overflow-hidden">
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
                className="h-full p-1"
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
                className="h-full p-1"
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
                className="h-full p-1"
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
    <StepFrame
      step={1}
      title="FIRST CONTACT PROTOCOL"
      actions={(
        <HUDButton onClick={onNext}>
          Initialize
        </HUDButton>
      )}
    >
      <div className="box-border h-full flex flex-col items-center justify-center gap-3 px-3 text-center">
        <div className="relative">
          <img
            src={appLogo}
            alt="Stellaris Companion logo"
            className="relative h-20 w-20 rounded-xl border border-accent-cyan/40 shadow-glow-sm drop-shadow-[0_0_26px_rgba(0,212,255,0.55)]"
          />
        </div>

        <div className="max-w-xl space-y-2">
          <p className="font-display text-base tracking-wide text-text-primary uppercase">
            Welcome to Stellaris Companion
          </p>
          <p className="text-sm text-text-secondary leading-relaxed">
            We will connect your advisor in two quick steps: API access and save data link.
          </p>
        </div>
      </div>
    </StepFrame>
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
    <StepFrame
      step={2}
      title="INTELLIGENCE UPLINK"
      actions={(
        <>
          <HUDButton variant="secondary" onClick={onBack}>
            Back
          </HUDButton>
          <HUDButton onClick={onNext} disabled={!hasKey}>
            Next
          </HUDButton>
        </>
      )}
    >
      <div className="mx-auto w-full max-w-2xl space-y-5">
        <div className="space-y-1">
          <HUDLabel className="text-accent-cyan/80">Required Credential</HUDLabel>
          <h2 className="font-display text-lg tracking-[0.1em] uppercase text-text-primary">
            Google Gemini API Key
          </h2>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">
          Your advisor runs on Google Gemini. You will need an API key. Setup takes about 30 seconds.
        </p>

        <div className="relative">
          <HUDInput
            label="API KEY TOKEN"
            type="password"
            placeholder="AIza..."
            value={apiKey}
            onChange={(e) => onChange(e.target.value)}
            statusText={hasKey ? 'READY' : 'MISSING'}
            statusClassName={hasKey ? 'text-accent-green' : 'text-accent-yellow'}
            autoFocus
          />
        </div>

        <a
          href="https://aistudio.google.com/app/apikey"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block font-display text-[10px] text-accent-cyan hover:underline tracking-wider"
        >
          GENERATE KEY &gt;
        </a>
      </div>
    </StepFrame>
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
    <StepFrame
      step={3}
      title="DATA LINK"
      actions={(
        <>
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
              <HUDButton variant="ghost" onClick={onComplete}>
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
        </>
      )}
    >
      <div className="mx-auto w-full max-w-2xl pt-2">
        <HUDLabel className="block mb-3 text-accent-cyan/80">Save Source</HUDLabel>
        <h2 className="font-display text-lg tracking-[0.1em] uppercase text-text-primary mb-5">
          Stellaris Save Directory
        </h2>
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
    </StepFrame>
  )
}

interface StepFrameProps {
  step: Step
  title: string
  children: ReactNode
  actions: ReactNode
}

function StepFrame({ step, title, children, actions }: StepFrameProps) {
  return (
    <div className="h-full">
      <HUDPanel
        className="relative h-full bg-bg-secondary/95 border border-accent-cyan/35 shadow-[0_0_40px_rgba(0,212,255,0.08),0_10px_28px_rgba(0,0,0,0.55)]"
        decoration="brackets"
        noPadding
      >
        <div className="grid h-full grid-rows-[auto_minmax(0,1fr)_auto] px-6 pt-4 pb-4">
          <div className="mb-3">
            <HUDMicro className="text-accent-cyan">{`STEP 0${step} / 03`}</HUDMicro>
            <h1 id="onboarding-step-title" className="mt-1.5 font-display text-xl tracking-[0.12em] uppercase text-text-primary">
              {title}
            </h1>
          </div>
          <div className="min-h-0 overflow-y-auto custom-scrollbar">
            {children}
          </div>
          <div className="mt-3 h-11 flex items-center justify-end gap-3 flex-nowrap [&>button]:h-11 [&>button]:min-w-[10rem]">
            {actions}
          </div>
        </div>
      </HUDPanel>
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
      <div className="p-4 bg-white/5 border border-white/10 rounded-sm">
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

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const selector = [
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    'a[href]',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ')

  return Array.from(container.querySelectorAll<HTMLElement>(selector))
    .filter((el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true')
}
