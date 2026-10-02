import { useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { HUDButton } from './hud/HUDButton'
import { OnboardingFrame, OnboardingIcon, OnboardingSpinner } from './OnboardingFrame'
import { OnboardingAdvisorActions, OnboardingAdvisorContent, onboardingAdvisorTitle, providerName, useOnboardingAdvisor } from './OnboardingAdvisorSetup'
import { MCPRelayPanel } from './settings/MCPRelayPanel'
import appLogo from '../assets/app_logo.svg'
import { useTranslation } from 'react-i18next'
import { LANGUAGE_OPTIONS } from '../i18n/languages'
import type { AdvisorProvider, LanguageSetting } from '../hooks/useSettings'

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
const emptySaves: SaveDetectionResult = { found: false, directory: null, saveCount: 0, latest: null }
export default function OnboardingModal({ onComplete, language, onLanguageSelect }: OnboardingModalProps) {
  const { t } = useTranslation()
  const reducedMotion = useReducedMotion()
  const [step, setStep] = useState<Step>(1)
  const [aiApps, setAIApps] = useState(false)
  const [connectedProvider, setConnectedProvider] = useState<AdvisorProvider | null>(null)
  const advisor = useOnboardingAdvisor(provider => { setConnectedProvider(provider); setStep(3) })
  const [saveResult, setSaveResult] = useState<SaveDetectionResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [fullLocation, setFullLocation] = useState(false)
  const [languageSaving, setLanguageSaving] = useState(false)
  const [languageError, setLanguageError] = useState(false)
  const [completionSaving, setCompletionSaving] = useState(false)
  const [completionError, setCompletionError] = useState(false)
  const [browseError, setBrowseError] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const scanRequest = useRef(0)
  const browseRequest = useRef(0)
  const selectedPathRef = useRef(selectedPath)
  selectedPathRef.current = selectedPath
  const detectSaves = useCallback(async (directory?: string) => {
    const id = ++scanRequest.current
    setScanning(true); setBrowseError(false)
    try {
      const result = directory ? await window.electronAPI?.onboarding.detectSavesInDir(directory) : await window.electronAPI?.onboarding.detectSaves()
      if (id !== scanRequest.current) return
      setSaveResult(result || emptySaves)
      if (result?.directory) setSelectedPath(result.directory)
    } catch {
      if (id === scanRequest.current) setSaveResult({ ...emptySaves, directory: directory || null })
    } finally { if (id === scanRequest.current) setScanning(false) }
  }, [])
  useEffect(() => {
    if (step !== 3) return
    void detectSaves(selectedPathRef.current || undefined)
    return () => { scanRequest.current++; browseRequest.current++ }
  }, [step, detectSaves])
  // A second scan catches saves arriving just after the initial folder check.
  const rescanned = useRef(false)
  useEffect(() => { rescanned.current = false }, [step])
  useEffect(() => {
    if (step !== 3 || scanning || !saveResult || saveResult.found || rescanned.current) return
    rescanned.current = true
    const timer = setTimeout(() => void detectSaves(selectedPathRef.current || undefined), 2000)
    return () => clearTimeout(timer)
  }, [step, scanning, saveResult, detectSaves])
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    return () => previous?.focus()
  }, [])
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const frame = requestAnimationFrame(() => {
      // Focus the action or form, rather than making keyboard users pass language first.
      const target = dialog.querySelector<HTMLElement>('[data-onboarding-primary]:not(:disabled), [data-onboarding-content] input, [data-onboarding-content] button')
      ;(target || dialog).focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [step, advisor.view, aiApps, scanning, saveResult?.found])
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]')).filter(node => node.getClientRects().length)
      const first = focusable[0], last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (!first) { event.preventDefault(); dialog.focus() }
      else if (event.shiftKey && (active === first || !dialog.contains(active))) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && (active === last || !dialog.contains(active))) { event.preventDefault(); first.focus() }
    }
    dialog.addEventListener('keydown', trap)
    return () => dialog.removeEventListener('keydown', trap)
  }, [])
  async function selectLanguage(value: string) {
    setLanguageSaving(true); setLanguageError(false)
    try { setLanguageError(!await onLanguageSelect(value as LanguageSetting)) }
    catch { setLanguageError(true) }
    finally { setLanguageSaving(false) }
  }
  async function browse() {
    // An automatic rescan may finish while the native folder picker is open.
    // Only leaving this step should invalidate the user's folder selection.
    const id = browseRequest.current
    try {
      const folder = await window.electronAPI?.showFolderDialog()
      if (folder && id === browseRequest.current) { setSelectedPath(folder); setFullLocation(false); await detectSaves(folder) }
    } catch { if (id === browseRequest.current) setBrowseError(true) }
  }
  async function complete(useFoundSaves: boolean) {
    if (completionSaving) return
    setCompletionSaving(true); setCompletionError(false)
    try {
      const api = window.electronAPI
      if (!api) throw new Error('unavailable')
      const saveDir = selectedPath || saveResult?.directory
      if (useFoundSaves && saveResult?.found && saveDir) {
        if (!(await api.saveSettings({ saveDir })).success) throw new Error('save')
      }
      if (!(await api.onboarding.complete()).success) throw new Error('complete')
      onComplete(aiApps)
    } catch { setCompletionError(true) }
    finally { setCompletionSaving(false) }
  }
  const languageMenu = <div className="flex shrink-0 flex-col items-end gap-1">
    <label htmlFor="onboarding-language" className="sr-only">{t('onboarding.language')}</label>
    <select id="onboarding-language" data-testid="onboarding-language" value={language} disabled={languageSaving || completionSaving}
      onChange={event => void selectLanguage(event.target.value)} className="h-8 w-[148px] max-w-full rounded border border-white/20 bg-bg-primary px-2 text-sm text-text-primary outline-none focus:border-accent-cyan">
      {LANGUAGE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.value === 'system' ? t('languages.system') : option.nativeLabel}</option>)}
    </select>{languageError && <p role="alert" className="max-w-[148px] text-xs text-accent-red">{t('onboarding.languageError')}</p>}
  </div>
  const title = step === 1 ? t('onboarding.welcome.stepTitle') : step === 2 ? (aiApps ? t('settings.aiSetup.routes.relay.title') : onboardingAdvisorTitle(advisor, t)) : t('onboarding.slim.findSaves')
  const path = selectedPath || saveResult?.directory || ''
  const shortPath = path.replace(/^(\/Users\/[^/]+|\/home\/[^/]+|C:\\Users\\[^\\]+)/, '~')
  const actions = step === 1 ? <><span /><HUDButton data-onboarding-primary="true" onClick={() => setStep(2)}>{t('onboarding.actions.initialize')}</HUDButton></>
    : step === 2 ? (aiApps ? <><HUDButton variant="secondary" onClick={() => setAIApps(false)}>{t('onboarding.actions.back')}</HUDButton><HUDButton data-onboarding-primary="true" onClick={() => setStep(3)}>{t('onboarding.actions.continue')}</HUDButton></> : <OnboardingAdvisorActions controller={advisor} onBack={() => setStep(1)} onSkip={() => { setConnectedProvider(null); setStep(3) }} />)
      : <><HUDButton variant="secondary" disabled={completionSaving} onClick={() => setStep(2)}>{t('onboarding.actions.back')}</HUDButton>
        {!scanning && (saveResult?.found ? <HUDButton data-onboarding-primary="true" disabled={completionSaving} onClick={() => void complete(true)}>{t('onboarding.slim.openCompanion')}</HUDButton>
          : <div className="ml-auto flex flex-wrap justify-end gap-2"><HUDButton variant="ghost" disabled={completionSaving} onClick={() => void complete(false)}>{t('onboarding.actions.setUpLater')}</HUDButton>
            <HUDButton data-onboarding-primary="true" disabled={completionSaving} onClick={() => void browse()}>{t('onboarding.slim.chooseFolder')}</HUDButton></div>)}</>
  return createPortal(<motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
    <motion.div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="onboarding-step-title" tabIndex={-1}
      initial={reducedMotion ? false : { opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ duration: 0.2 }}
      className="relative w-full max-w-[704px] outline-none" style={{ height: 'min(500px, calc(100dvh - 32px))' }}>
      <OnboardingFrame step={step} title={title} languageMenu={languageMenu} actions={actions}>
        {step === 1 ? <div className="flex flex-1 flex-col items-center justify-center gap-4 py-3 text-center">
          <img src={appLogo} alt={t('onboarding.logoAlt')} className="h-20 w-20" style={{ filter: 'var(--theme-logo-filter) drop-shadow(0 0 20px rgb(var(--color-accent-cyan) / 0.4))' }} />
          <div className="space-y-2"><p className="font-display text-base leading-6 tracking-[0.04em] uppercase text-text-primary">{t('onboarding.welcome.title')}</p>
            <p className="text-sm leading-5 text-text-secondary">{t('onboarding.welcome.description')}</p></div>
        </div> : step === 2 ? (aiApps ? <MCPRelayPanel onChooseCampaign={() => setStep(3)} /> : <OnboardingAdvisorContent controller={advisor} onSkip={() => { setConnectedProvider(null); setStep(3) }} onConnectAIApps={() => setAIApps(true)} />)
          : <div className="flex flex-1 flex-col gap-4 py-1">
            {connectedProvider && <p className="self-start rounded border border-accent-green/30 bg-accent-green/10 px-2 py-1 font-mono text-xs text-accent-green">{t('onboarding.slim.providerConnected', { provider: connectedProvider === 'custom' ? t('onboarding.slim.customEndpoint') : providerName(connectedProvider) })}</p>}
            {scanning ? <div role="status" aria-live="polite" className="flex flex-1 flex-col items-center justify-center gap-4 py-3"><OnboardingIcon kind="folder" className="h-12 w-12" /><p className="flex items-center gap-3 text-lg"><OnboardingSpinner />{t('onboarding.slim.findingSaves')}</p></div>
              : saveResult?.found ? <div className="flex flex-1 flex-col justify-center gap-4">
                <div className="flex items-center justify-between gap-4 border-y border-white/10 py-4">
                  <div className="flex min-w-0 items-center gap-4"><OnboardingIcon kind="folder" className="h-9 w-9" /><div className="min-w-0"><p className="text-lg font-medium leading-6">{t('onboarding.slim.folderLabel')}</p><p className="mt-1 truncate font-mono text-xs text-text-secondary" title={path}>{shortPath}</p></div></div>
                  <p className="shrink-0 font-mono text-xs text-accent-green">{t('onboarding.slim.foundCount', { count: saveResult.saveCount })}</p>
                </div>
                {fullLocation && <p className="break-all font-mono text-xs text-text-secondary">{path}</p>}
                <div className="flex flex-wrap justify-between gap-3"><button type="button" className="text-sm text-accent-cyan hover:underline" onClick={() => setFullLocation(!fullLocation)}>{t(fullLocation ? 'onboarding.slim.hideLocation' : 'onboarding.slim.showLocation')}</button>
                  <button type="button" className="text-sm text-accent-cyan hover:underline" disabled={completionSaving} onClick={() => void browse()}>{t('onboarding.slim.chooseAnother')}</button></div>
              </div> : <div className="flex flex-1 flex-col items-center justify-center gap-4 py-3 text-center"><OnboardingIcon kind="folder" className="h-12 w-12" /><p className="text-xl leading-7">{t('onboarding.slim.noSaves')}</p><p className="text-sm leading-5 text-text-secondary">{t('onboarding.slim.noSavesHint')}</p>
                <button type="button" className="text-sm text-accent-cyan hover:underline" disabled={completionSaving} onClick={() => void detectSaves(selectedPath || undefined)}>{t('onboarding.actions.scanAgain')}</button></div>}
            {(completionError || browseError) && <p role="alert" className="text-sm text-accent-red">{t(completionError ? 'onboarding.completionError' : 'onboarding.slim.browseError')}</p>}
          </div>}
      </OnboardingFrame>
    </motion.div>
  </motion.div>, document.body)
}
