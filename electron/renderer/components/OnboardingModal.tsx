import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { HUDButton } from './hud/HUDButton'
import { HUDLabel, HUDMicro } from './hud/HUDText'
import { HUDPanel } from './hud/HUDPanel'
import { AISetupForm } from './settings/AISetupForm'
import {
  useSettings,
} from '../hooks/useSettings'
import appLogo from '../assets/app_logo.svg'
import { LANGUAGE_OPTIONS } from '../i18n/languages'
import type { LanguageSetting } from '../hooks/useSettings'

interface OnboardingModalProps {
  onComplete: (openAIApps?: boolean) => void
  language: LanguageSetting
  onLanguageSelect: (language: LanguageSetting) => Promise<boolean>
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

const ACTION_ROW_DRIFT_TOLERANCE_PX = 2

export default function OnboardingModal({ onComplete, language, onLanguageSelect }: OnboardingModalProps) {
  const { t } = useTranslation()
  const [step, setStep] = useState<Step>(1)
  const [direction, setDirection] = useState(1)
  const autoRescanAttemptedRef = useRef(false)
  const autoRescanTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const actionRowBaselineTopRef = useRef<number | null>(null)

  const { settings, loading: settingsLoading, saveSettings } = useSettings()
  const [useAIApp, setUseAIApp] = useState(false)

  // Step 3 state
  const [saveResult, setSaveResult] = useState<SaveDetectionResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [languageSaving, setLanguageSaving] = useState(false)
  const [languageError, setLanguageError] = useState(false)
  const [completionSaving, setCompletionSaving] = useState(false)
  const [completionError, setCompletionError] = useState(false)

  async function selectLanguage(value: string) {
    setLanguageSaving(true)
    setLanguageError(false)
    try {
      setLanguageError(!await onLanguageSelect(value as LanguageSetting))
    } catch {
      setLanguageError(true)
    } finally {
      setLanguageSaving(false)
    }
  }

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

  useEffect(() => {
    if (!import.meta.env.DEV) return
    const dialog = dialogRef.current
    if (!dialog) return

    const rafId = requestAnimationFrame(() => {
      const frame = dialog.querySelector<HTMLElement>(`[data-onboarding-frame-step="${step}"]`)
      const actionRow = frame?.querySelector<HTMLElement>('[data-onboarding-actions-row="true"]')
      if (!actionRow) return

      const top = Math.round(actionRow.getBoundingClientRect().top)
      const baseline = actionRowBaselineTopRef.current
      if (baseline === null) {
        actionRowBaselineTopRef.current = top
        return
      }

      const delta = top - baseline
      if (Math.abs(delta) > ACTION_ROW_DRIFT_TOLERANCE_PX) {
        console.warn('[OnboardingModal] action row vertical drift detected', {
          step,
          baselineTop: baseline,
          currentTop: top,
          delta,
        })
      }
    })

    return () => cancelAnimationFrame(rafId)
  }, [
    step,
    scanning,
    saveResult?.found,
  ])

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

  async function handleComplete(useFoundSaves: boolean) {
    if (completionSaving) return
    setCompletionSaving(true)
    setCompletionError(false)
    try {
      if (!window.electronAPI) throw new Error('Electron API unavailable')
      const settingsToSave: Record<string, string> = {}
      if (useFoundSaves && saveResult?.found) {
        const saveDir = selectedPath || saveResult.directory
        if (saveDir) settingsToSave.saveDir = saveDir
      }
      if (Object.keys(settingsToSave).length) {
        const saved = await window.electronAPI.saveSettings(settingsToSave)
        if (saved?.success === false) throw new Error('Settings save failed')
      }
      const completed = await window.electronAPI.onboarding.complete()
      if (completed?.success === false) throw new Error('Onboarding completion failed')
      onComplete(useAIApp)
    } catch {
      setCompletionError(true)
    } finally {
      setCompletionSaving(false)
    }
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
        className="relative mx-4 h-[min(36rem,calc(100vh-3rem))] w-[min(54rem,calc(100%-2rem))] outline-none"
      >
        <div className="relative h-full overflow-hidden">
          <div className="absolute right-6 top-5 z-10 flex flex-col items-end gap-1">
            <label htmlFor="onboarding-language" className="sr-only">{t('onboarding.language')}</label>
            <select id="onboarding-language" data-testid="onboarding-language" value={language} disabled={languageSaving} onChange={event => void selectLanguage(event.target.value)} className="max-w-[11rem] rounded border border-accent-cyan/40 bg-bg-secondary px-2 py-1 text-sm text-text-primary">
              {LANGUAGE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.value === 'system' ? t('languages.system') : option.nativeLabel}</option>)}
            </select>
            {languageError && <p role="alert" className="text-xs text-accent-red">{t('onboarding.languageError')}</p>}
          </div>
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
                <StepFrame
                  step={2}
                  title={t('onboarding.ai.frameTitle')}
                  actions={<>
                    <HUDButton variant="secondary" onClick={() => goTo(1)}>{t('onboarding.actions.back')}</HUDButton>
                    <HUDButton variant="secondary" onClick={() => goTo(3)}>{t('onboarding.actions.later')}</HUDButton>
                  </>}
                >
                  {settingsLoading ? <p>{t('common.loading')}</p> : (
                    <AISetupForm
                      initialSettings={settings}
                      onSave={saveSettings}
                      onSaved={() => { setUseAIApp(false); goTo(3) }}
                      onUseAIApp={() => { setUseAIApp(true); goTo(3) }}
                    />
                  )}
                </StepFrame>
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
                  completing={completionSaving}
                  completionError={completionError}
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
  const { t } = useTranslation()
  return (
    <StepFrame
      step={1}
      title={t('onboarding.welcome.frameTitle')}
      actions={(
        <HUDButton data-onboarding-primary="true" onClick={onNext}>
          {t('onboarding.actions.start')}
        </HUDButton>
      )}
    >
      <div className="box-border h-full flex flex-col items-center justify-center gap-3 px-3 text-center">
        <div className="relative">
          <img
            src={appLogo}
            alt={t('onboarding.welcome.logoAlt')}
            className="relative h-20 w-20 rounded-xl border border-accent-cyan/40 shadow-glow-sm"
            style={{ filter: 'var(--theme-logo-filter) drop-shadow(0 0 26px rgb(var(--color-accent-cyan) / 0.55))' }}
          />
        </div>

        <div className="max-w-xl space-y-2">
          <p className="font-display text-base tracking-wide text-text-primary uppercase">
            {t('onboarding.welcome.title')}
          </p>
          <p className="text-sm text-text-secondary leading-relaxed">
            {t('onboarding.welcome.body')}
          </p>
        </div>
      </div>
    </StepFrame>
  )
}

// =============================================================================
// Step 2: AI setup
// =============================================================================

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
  completing,
  completionError,
}: {
  scanning: boolean
  saveResult: SaveDetectionResult | null
  selectedPath: string | null
  shortenPath: (p: string) => string
  onBrowse: () => void
  onRetry: () => void
  onBack: () => void
  onComplete: (useFoundSaves: boolean) => void
  completing: boolean
  completionError: boolean
}) {
  const { t } = useTranslation()
  return (
    <StepFrame
      step={3}
      title={t('onboarding.saves.frameTitle')}
      actions={(
        <>
          <HUDButton variant="secondary" onClick={onBack} disabled={completing}>
            {t('onboarding.actions.back')}
          </HUDButton>
          {scanning ? null : saveResult?.found ? (
            <>
              <HUDButton variant="secondary" onClick={onBrowse} disabled={completing}>
                {t('onboarding.saves.browseElsewhere')}
              </HUDButton>
              <HUDButton data-onboarding-primary="true" onClick={() => onComplete(true)} disabled={completing}>
                {t('onboarding.actions.finish')}
              </HUDButton>
            </>
          ) : (
            <>
              <HUDButton variant="ghost" onClick={() => onComplete(false)} disabled={completing}>
                {t('onboarding.actions.later')}
              </HUDButton>
              <HUDButton variant="secondary" onClick={onRetry} disabled={completing}>
                {t('onboarding.saves.scanAgain')}
              </HUDButton>
              <HUDButton data-onboarding-primary="true" onClick={onBrowse} disabled={completing}>
                {t('onboarding.saves.browseFolder')}
              </HUDButton>
            </>
          )}
        </>
      )}
    >
      <div className="mx-auto w-full max-w-2xl pt-2">
        {completionError && <p role="alert" className="mb-3 text-sm text-accent-red">{t('onboarding.completionError')}</p>}
        <HUDLabel className="block mb-3 text-accent-cyan/80">{t('onboarding.saves.label')}</HUDLabel>
        <h2 className="font-display text-lg tracking-[0.1em] uppercase text-text-primary mb-5 break-words">
          {t('onboarding.saves.title')}
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
  const { t } = useTranslation()
  return (
    <div data-onboarding-frame-step={step} className="h-full">
      <HUDPanel
        className="relative h-full bg-bg-secondary/95 border border-accent-cyan/35 shadow-panel-cyan-soft"
        decoration="brackets"
        noPadding
      >
        <div className="grid h-full min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)_auto] px-6 pt-4 pb-4">
          <div className="mb-3 pr-44">
            <HUDMicro className="text-accent-cyan">
              {t('onboarding.step', { current: `0${step}`, total: '03' })}
            </HUDMicro>
            <h1 id="onboarding-step-title" className="mt-1.5 font-display text-xl tracking-[0.12em] uppercase text-text-primary">
              {title}
            </h1>
          </div>
          <div className="min-h-0 min-w-0 overflow-y-auto overflow-x-hidden custom-scrollbar">
            {children}
          </div>
          <div
            data-onboarding-actions-row="true"
            className="mt-3 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:justify-end [&>button]:min-h-11 [&>button]:min-w-0 [&>button]:px-3 sm:[&>button]:min-w-[8rem]"
          >
            {actions}
          </div>
        </div>
      </HUDPanel>
    </div>
  )
}

function SaveScanning() {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-3 py-8">
      <div className="w-3 h-3 border border-accent-cyan border-t-transparent rounded-full animate-spin" />
      <span className="text-sm text-text-secondary">{t('onboarding.saves.scanning')}</span>
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
  const { t } = useTranslation()
  const displayPath = selectedPath || result.directory
  return (
    <div className="space-y-4">
      <p className="text-sm text-text-primary">{t('onboarding.saves.found')}</p>
      <div className="p-4 bg-white/5 border border-white/10 rounded-sm">
        <div className="font-mono text-xs text-accent-cyan mb-1 break-all">
          {displayPath ? shortenPath(displayPath) : ''}
        </div>
        <div className="text-xs text-text-secondary">
          {t('onboarding.saves.count', { count: result.saveCount })}
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
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      <p className="text-sm text-text-primary leading-relaxed">
        {t('onboarding.saves.notFound')}
      </p>
      <p className="text-sm text-text-secondary leading-relaxed break-all">
        {selectedPath
          ? t('onboarding.saves.notFoundIn', { path: shortenPath(selectedPath) })
          : t('onboarding.saves.notFoundDefault')}
      </p>
      <p className="text-sm text-text-secondary leading-relaxed">
        {t('onboarding.saves.notFoundHelp')}
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
