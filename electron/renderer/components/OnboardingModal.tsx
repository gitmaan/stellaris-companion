import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { HUDButton } from './hud/HUDButton'
import { HUDInput } from './hud/HUDInput'
import { HUDSelect } from './hud/HUDForm'
import { HUDLabel, HUDMicro } from './hud/HUDText'
import { HUDPanel } from './hud/HUDPanel'
import { AdvisorProviderChooser } from './settings/AdvisorProviderChooser'
import { ProviderSetupGuide } from './settings/ProviderSetupGuide'
import {
  DEFAULT_ADVISOR_PROVIDER,
  normalizeAdvisorProvider,
  type AdvisorProvider,
} from '../hooks/useSettings'
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

interface AdvisorProviderModel {
  id: string
  name: string
  recommended?: boolean
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

export default function OnboardingModal({ onComplete }: OnboardingModalProps) {
  const { t } = useTranslation()
  const [step, setStep] = useState<Step>(1)
  const [direction, setDirection] = useState(1)
  const autoRescanAttemptedRef = useRef(false)
  const autoRescanTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const actionRowBaselineTopRef = useRef<number | null>(null)

  // Step 2 state
  const [advisorProvider, setAdvisorProvider] = useState<AdvisorProvider>(DEFAULT_ADVISOR_PROVIDER)
  const [googleApiKey, setGoogleApiKey] = useState('')
  const [openRouterApiKey, setOpenRouterApiKey] = useState('')
  const [customProviderApiKey, setCustomProviderApiKey] = useState('')
  const [advisorBaseUrl, setAdvisorBaseUrl] = useState('')
  const [advisorModel, setAdvisorModel] = useState('')
  const [advisorModels, setAdvisorModels] = useState<AdvisorProviderModel[]>([])
  const [advisorChecking, setAdvisorChecking] = useState(false)
  const [advisorConnectionMessage, setAdvisorConnectionMessage] = useState<string | null>(null)
  const [advisorConnectionOk, setAdvisorConnectionOk] = useState(false)

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
    advisorProvider,
    googleApiKey,
    openRouterApiKey,
    customProviderApiKey,
    advisorBaseUrl,
    advisorModel,
  ])

  const invalidateAdvisorConnection = () => {
    setAdvisorModels([])
    setAdvisorModel('')
    setAdvisorConnectionMessage(null)
    setAdvisorConnectionOk(false)
  }

  const handleAdvisorProviderChange = (rawValue: string) => {
    const nextProvider = normalizeAdvisorProvider(rawValue)
    if (nextProvider === advisorProvider) return
    setAdvisorProvider(nextProvider)
    setAdvisorBaseUrl('')
    invalidateAdvisorConnection()
  }

  const handleOpenRouterApiKeyChange = (value: string) => {
    setOpenRouterApiKey(value)
    invalidateAdvisorConnection()
  }

  const handleCustomProviderApiKeyChange = (value: string) => {
    setCustomProviderApiKey(value)
    invalidateAdvisorConnection()
  }

  const handleAdvisorBaseUrlChange = (value: string) => {
    setAdvisorBaseUrl(value)
    invalidateAdvisorConnection()
  }

  const handleFindAdvisorModels = async () => {
    if (!window.electronAPI?.advisorProviders?.listModels || advisorProvider === 'gemini') return
    const apiKey = advisorProvider === 'openrouter'
      ? openRouterApiKey
      : advisorProvider === 'custom'
        ? customProviderApiKey
        : ''
    setAdvisorChecking(true)
    setAdvisorConnectionMessage(null)
    setAdvisorConnectionOk(false)
    try {
      const result = await window.electronAPI.advisorProviders.listModels({
        provider: advisorProvider,
        baseUrl: advisorBaseUrl,
        apiKey,
      })
      if (!result.ok) {
        setAdvisorModels([])
        setAdvisorConnectionMessage(result.error || t('onboarding.ai.connectionError'))
        return
      }
      const models = (result.models || []) as AdvisorProviderModel[]
      setAdvisorModels(models)
      const suggested = models.find(model => model.recommended) || (models.length === 1 ? models[0] : null)
      if (suggested) setAdvisorModel(suggested.id)
      setAdvisorConnectionOk(true)
      setAdvisorConnectionMessage(
        models.length
          ? t('onboarding.ai.modelsFound', { count: models.length })
          : t('onboarding.ai.noModels'),
      )
    } catch {
      setAdvisorConnectionMessage(t('onboarding.ai.connectionError'))
    } finally {
      setAdvisorChecking(false)
    }
  }

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
    const settingsToSave: Record<string, string> = {
      advisorProvider,
      advisorModel,
      advisorBaseUrl,
      saveDir: selectedPath || '',
    }
    if (googleApiKey) settingsToSave.googleApiKey = googleApiKey
    if (openRouterApiKey) settingsToSave.openRouterApiKey = openRouterApiKey
    if (customProviderApiKey) settingsToSave.customProviderApiKey = customProviderApiKey
    await window.electronAPI?.saveSettings(settingsToSave)

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
        className="relative mx-4 h-[min(36rem,calc(100vh-3rem))] w-[min(54rem,calc(100%-2rem))] outline-none"
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
                <StepAiSetup
                  provider={advisorProvider}
                  googleApiKey={googleApiKey}
                  openRouterApiKey={openRouterApiKey}
                  customProviderApiKey={customProviderApiKey}
                  baseUrl={advisorBaseUrl}
                  model={advisorModel}
                  models={advisorModels}
                  checking={advisorChecking}
                  connectionOk={advisorConnectionOk}
                  connectionMessage={advisorConnectionMessage}
                  onProviderChange={handleAdvisorProviderChange}
                  onGoogleApiKeyChange={setGoogleApiKey}
                  onOpenRouterApiKeyChange={handleOpenRouterApiKeyChange}
                  onCustomProviderApiKeyChange={handleCustomProviderApiKeyChange}
                  onBaseUrlChange={handleAdvisorBaseUrlChange}
                  onModelChange={setAdvisorModel}
                  onFindModels={() => void handleFindAdvisorModels()}
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

function StepAiSetup({
  provider,
  googleApiKey,
  openRouterApiKey,
  customProviderApiKey,
  baseUrl,
  model,
  models,
  checking,
  connectionOk,
  connectionMessage,
  onProviderChange,
  onGoogleApiKeyChange,
  onOpenRouterApiKeyChange,
  onCustomProviderApiKeyChange,
  onBaseUrlChange,
  onModelChange,
  onFindModels,
  onBack,
  onNext,
}: {
  provider: AdvisorProvider
  googleApiKey: string
  openRouterApiKey: string
  customProviderApiKey: string
  baseUrl: string
  model: string
  models: AdvisorProviderModel[]
  checking: boolean
  connectionOk: boolean
  connectionMessage: string | null
  onProviderChange: (value: string) => void
  onGoogleApiKeyChange: (value: string) => void
  onOpenRouterApiKeyChange: (value: string) => void
  onCustomProviderApiKeyChange: (value: string) => void
  onBaseUrlChange: (value: string) => void
  onModelChange: (value: string) => void
  onFindModels: () => void
  onBack: () => void
  onNext: () => void
}) {
  const { t } = useTranslation()
  const isGemini = provider === 'gemini'
  const hasSetup = isGemini
    ? googleApiKey.trim().length > 0
    : connectionOk && model.trim().length > 0
  const modelOptions = [
    { value: '', label: t('onboarding.ai.chooseModel') },
    ...models.slice(0, 100).map(option => ({ value: option.id, label: option.name || option.id })),
  ]

  return (
    <StepFrame
      step={2}
      title={t('onboarding.ai.frameTitle')}
      actions={(
        <>
          <HUDButton variant="secondary" onClick={onBack}>
            {t('onboarding.actions.back')}
          </HUDButton>
          {!hasSetup && (
            <HUDButton variant="secondary" onClick={onNext}>
              {t('onboarding.actions.later')}
            </HUDButton>
          )}
          <HUDButton data-onboarding-primary="true" onClick={onNext} disabled={!hasSetup}>
            {t('onboarding.actions.continue')}
          </HUDButton>
        </>
      )}
    >
      <div className="mx-auto w-full max-w-4xl space-y-4">
        <AdvisorProviderChooser provider={provider} onChange={value => onProviderChange(value)} />
        <ProviderSetupGuide provider={provider} />

        {isGemini ? (
          <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
            <HUDInput
              label={t('onboarding.ai.geminiKey')}
              type="password"
              placeholder="AIza..."
              value={googleApiKey}
              onChange={(event) => onGoogleApiKeyChange(event.target.value)}
              statusText={hasSetup ? t('onboarding.ai.ready') : t('onboarding.ai.notSet')}
              statusClassName={hasSetup ? 'text-accent-green' : 'text-accent-yellow'}
              autoFocus
            />
            <a
              href="https://aistudio.google.com/app/apikey"
              target="_blank"
              rel="noopener noreferrer"
              className="pb-3 font-display text-[10px] tracking-wider text-accent-cyan hover:underline"
            >
              {t('onboarding.ai.getGeminiKey')} &gt;
            </a>
          </div>
        ) : (
          <div className="space-y-3 border-t border-white/10 pt-3">
            {provider === 'openrouter' && (
              <HUDInput
                label={t('onboarding.ai.providerKey')}
                type="password"
                value={openRouterApiKey}
                onChange={(event) => onOpenRouterApiKeyChange(event.target.value)}
                placeholder={t('onboarding.ai.enterKey')}
              />
            )}
            {provider === 'custom' && (
              <div className="grid gap-3 sm:grid-cols-2">
                <HUDInput
                  label={t('onboarding.ai.serverAddress')}
                  value={baseUrl}
                  onChange={(event) => onBaseUrlChange(event.target.value)}
                  placeholder="https://provider.example/v1"
                />
                <HUDInput
                  label={t('onboarding.ai.optionalKey')}
                  type="password"
                  value={customProviderApiKey}
                  onChange={(event) => onCustomProviderApiKeyChange(event.target.value)}
                  placeholder={t('onboarding.ai.optional')}
                />
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <HUDButton type="button" variant="secondary" onClick={onFindModels} disabled={checking}>
                {checking ? t('onboarding.ai.looking') : t('onboarding.ai.findModels')}
              </HUDButton>
              {connectionMessage && (
                <HUDMicro className={connectionOk ? 'text-accent-green' : 'text-accent-red'}>
                  {connectionMessage}
                </HUDMicro>
              )}
            </div>
            {models.length > 0 ? (
              <HUDSelect
                label={t('onboarding.ai.model')}
                value={model}
                onChange={event => onModelChange(event.target.value)}
                options={modelOptions}
              />
            ) : (
              <HUDInput
                label={t('onboarding.ai.model')}
                value={model}
                onChange={event => onModelChange(event.target.value)}
                placeholder={t('onboarding.ai.findModelsFirst')}
              />
            )}
          </div>
        )}
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
  const { t } = useTranslation()
  return (
    <StepFrame
      step={3}
      title={t('onboarding.saves.frameTitle')}
      actions={(
        <>
          <HUDButton variant="secondary" onClick={onBack}>
            {t('onboarding.actions.back')}
          </HUDButton>
          {scanning ? null : saveResult?.found ? (
            <>
              <HUDButton variant="secondary" onClick={onBrowse}>
                {t('onboarding.saves.browseElsewhere')}
              </HUDButton>
              <HUDButton data-onboarding-primary="true" onClick={onComplete}>
                {t('onboarding.actions.finish')}
              </HUDButton>
            </>
          ) : (
            <>
              <HUDButton variant="ghost" onClick={onComplete}>
                {t('onboarding.actions.later')}
              </HUDButton>
              <HUDButton variant="secondary" onClick={onRetry}>
                {t('onboarding.saves.scanAgain')}
              </HUDButton>
              <HUDButton data-onboarding-primary="true" onClick={onBrowse}>
                {t('onboarding.saves.browseFolder')}
              </HUDButton>
            </>
          )}
        </>
      )}
    >
      <div className="mx-auto w-full max-w-2xl pt-2">
        <HUDLabel className="block mb-3 text-accent-cyan/80">{t('onboarding.saves.label')}</HUDLabel>
        <h2 className="font-display text-lg tracking-[0.1em] uppercase text-text-primary mb-5">
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
        <div className="grid h-full grid-rows-[auto_minmax(0,1fr)_auto] px-6 pt-4 pb-4">
          <div className="mb-3">
            <HUDMicro className="text-accent-cyan">
              {t('onboarding.step', { current: `0${step}`, total: '03' })}
            </HUDMicro>
            <h1 id="onboarding-step-title" className="mt-1.5 font-display text-xl tracking-[0.12em] uppercase text-text-primary">
              {title}
            </h1>
          </div>
          <div className="min-h-0 overflow-y-auto custom-scrollbar">
            {children}
          </div>
          <div
            data-onboarding-actions-row="true"
            className="mt-3 h-11 flex items-center justify-end gap-3 flex-nowrap [&>button]:h-11 [&>button]:min-w-[10rem]"
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
        <div className="font-mono text-xs text-accent-cyan mb-1">
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
      <p className="text-sm text-text-secondary leading-relaxed">
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
