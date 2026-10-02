import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { AdvisorProvider, Settings } from '../hooks/useSettings'
import { useChatGPT } from '../hooks/useChatGPT'
import { HUDButton } from './hud/HUDButton'
import { OnboardingIcon, OnboardingSpinner } from './OnboardingFrame'
import chatgptLogo from '../assets/chatgpt-logo-white.svg'

type View = 'choice' | 'gemini' | 'openrouter' | 'local' | 'models' | 'details' | 'custom' | 'connecting' | 'error'
type Draft = { apiKey: string; baseUrl: string; model: string; credentialId?: string }
type Model = { id: string; name: string; recommended?: boolean }
const presets = { ollama: 'http://127.0.0.1:11434/v1', lm_studio: 'http://127.0.0.1:1234/v1' }
const customUrlHint = 'http://127.0.0.1:8080/v1'
export const providerName = (provider: AdvisorProvider) => ({ chatgpt: 'ChatGPT', gemini: 'Gemini', openrouter: 'OpenRouter', ollama: 'Ollama', lm_studio: 'LM Studio', custom: 'Custom' })[provider]

// The controller lives in the wizard, so navigating to saves and back keeps drafts.
export function useOnboardingAdvisor(onConnected: (provider: AdvisorProvider) => void) {
  const { t } = useTranslation()
  const { status, accept } = useChatGPT()
  const [view, setView] = useState<View>('choice')
  const [provider, setProvider] = useState<AdvisorProvider>('chatgpt')
  const [drafts, setDrafts] = useState<Record<AdvisorProvider, Draft>>(() => Object.fromEntries(
    ['chatgpt', 'gemini', 'openrouter', 'ollama', 'lm_studio', 'custom'].map(id => [id, { apiKey: '', baseUrl: presets[id as keyof typeof presets] || '', model: '' }]),
  ) as Record<AdvisorProvider, Draft>)
  const [storedKeys, setStoredKeys] = useState<Record<string, boolean>>({})
  const [models, setModels] = useState<Model[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [browserConnecting, setBrowserConnecting] = useState(false)
  const browserPending = useRef(false)
  const request = useRef(0)
  const connected = useRef(onConnected)
  connected.current = onConnected
  const returnView = useRef<View>('choice')
  const retry = useRef<() => void>(() => {})
  useEffect(() => {
    let live = true
    void window.electronAPI?.getSettings().then(raw => {
      if (!live) return
      const settings = raw as Settings
      setStoredKeys({ gemini: !!settings.googleApiKeySet, openrouter: !!settings.openRouterApiKeySet,
        custom: !!settings.customProviderApiKeySet, ollama: !!settings.customProviderApiKeySet, lm_studio: !!settings.customProviderApiKeySet })
      const id = settings.advisorProvider
      if (id && id !== 'chatgpt') setDrafts(current => ({ ...current, [id]: { ...current[id],
        baseUrl: current[id].baseUrl === (presets[id as keyof typeof presets] || '') ? settings.advisorBaseUrl || current[id].baseUrl : current[id].baseUrl,
        model: current[id].model || settings.advisorModel || '',
      } }))
    }).catch(() => {})
    return () => { live = false; request.current++; if (browserPending.current) void window.electronAPI?.advisorProviders.cancelOpenRouter() }
  }, [])
  function update(field: keyof Draft, value: string) {
    setDrafts(current => ({ ...current, [provider]: { ...current[provider], [field]: value, ...(field === 'apiKey' ? { credentialId: undefined } : {}) } }))
  }
  function choose(next: AdvisorProvider, nextView: View) {
    request.current++
    setProvider(next); setView(nextView); setError(''); setModels([])
  }
  async function cancel() {
    request.current++
    if (browserPending.current) {
      browserPending.current = false; setBrowserConnecting(false)
      await window.electronAPI?.advisorProviders.cancelOpenRouter()
    }
    if (provider === 'chatgpt' && view === 'connecting') {
      setCancelling(true)
      try { const result = await window.electronAPI?.chatgpt.cancel(); if (result) accept(result) } catch { /* The stale result is also ignored locally. */ }
      finally { setCancelling(false) }
    }
    setView('choice'); setError('')
  }
  function fail(id: number, message: string) {
    if (id !== request.current) return
    setError(message); setView('error')
  }
  async function persist(id: number, selected: AdvisorProvider, model: string, baseUrl: string, credentialId?: string) {
    if (id !== request.current) return
    setSaving(true)
    try {
      const key = drafts[selected].apiKey.trim()
      const values: Partial<Settings> & { openRouterCredentialId?: string } = { advisorProvider: selected, advisorModel: model, advisorBaseUrl: baseUrl }
      if (key) {
        if (selected === 'gemini') values.googleApiKey = key
        else if (selected === 'openrouter') values.openRouterApiKey = key
        else values.customProviderApiKey = key
      }
      if (selected === 'openrouter' && credentialId) { values.openRouterCredentialId = credentialId; values.openRouterApiKey = '' }
      const result = await window.electronAPI?.saveSettings(values)
      if (!result?.success) throw new Error('save')
      if (id === request.current) { setView('choice'); connected.current(selected) }
    } catch { fail(id, t('onboarding.slim.saveError')) }
    finally { setSaving(false) }
  }
  async function startChatGPT() {
    const id = ++request.current
    setProvider('chatgpt'); setView('connecting'); setError(''); returnView.current = 'choice'
    retry.current = () => void startChatGPT()
    try {
      const api = window.electronAPI?.chatgpt
      if (!api) throw new Error('unavailable')
      const result = await (status?.ready ? api.check() : api.connect())
      if (id !== request.current) return
      accept(result)
      if (result.ok && result.status.ready) { setView('choice'); connected.current('chatgpt') }
      else fail(id, t(`chatgpt.errors.${result.code || 'CHATGPT_UNAVAILABLE'}`))
    } catch { fail(id, t('chatgpt.errors.CHATGPT_UNAVAILABLE')) }
  }
  async function connectModel(id: number, selected: AdvisorProvider, model: string, baseUrl: string, credentialId = drafts[selected].credentialId) {
    const result = await window.electronAPI?.advisorProviders.testModel({ provider: selected, model, baseUrl, apiKey: drafts[selected].apiKey.trim() || undefined, credentialId })
    if (id !== request.current) return
    if (!result?.ok) { fail(id, result?.error || t('onboarding.slim.connectionHelp')); return }
    if (!result.chronicleReady) { fail(id, t('onboarding.slim.modelLimited')); return }
    await persist(id, selected, selected === 'gemini' ? '' : result.model || model, result.baseUrl || baseUrl, credentialId)
  }
  async function connect(selected = provider, origin: View = view, draft = drafts[selected]) {
    if ((selected === 'gemini' || selected === 'openrouter') && !draft.apiKey.trim() && !storedKeys[selected] && !draft.credentialId) return
    if (selected === 'custom' && (!draft.baseUrl.trim() || !draft.model.trim())) return
    const id = ++request.current
    returnView.current = origin; setError(''); setView('connecting')
    retry.current = () => void connect(selected, origin, draft)
    try {
      if (selected === 'custom' || origin === 'models') {
        await connectModel(id, selected, draft.model.trim(), draft.baseUrl.trim()); return
      }
      const result = await window.electronAPI?.advisorProviders.listModels({ provider: selected,
        baseUrl: draft.baseUrl.trim() || undefined, apiKey: draft.apiKey.trim() || undefined, credentialId: draft.credentialId })
      if (id !== request.current) return
      if (!result?.ok) { fail(id, result?.error || t('onboarding.slim.connectionHelp')); return }
      if (selected === 'gemini') { await connectModel(id, selected, '', ''); return }
      const found = result.models || []
      if (!found.length) { fail(id, t('onboarding.slim.noModels')); return }
      const model = found.find(item => item.id === draft.model) || found.find(item => item.recommended) || found[0]
      const baseUrl = result.baseUrl || draft.baseUrl
      setModels(found)
      setDrafts(current => ({ ...current, [selected]: { ...current[selected], model: model.id, baseUrl } }))
      if (selected !== 'openrouter' && found.length > 1) { setView('models'); return }
      await connectModel(id, selected, model.id, baseUrl, draft.credentialId)
    } catch { fail(id, t('onboarding.slim.connectionHelp')) }
  }
  async function connectBrowser() {
    const id = ++request.current
    returnView.current = 'openrouter'; setError(''); setView('connecting')
    browserPending.current = true; setBrowserConnecting(true)
    try {
      const result = await window.electronAPI?.advisorProviders.connectOpenRouter()
      if (id !== request.current) return
      browserPending.current = false; setBrowserConnecting(false)
      if (!result?.ok || !result.credentialId) { fail(id, t('onboarding.slim.connectionHelp')); return }
      const draft = { ...drafts.openrouter, apiKey: '', credentialId: result.credentialId }
      setDrafts(current => ({ ...current, openrouter: draft }))
      await connect('openrouter', 'openrouter', draft)
    } catch { fail(id, t('onboarding.slim.connectionHelp')) }
    finally { if (id === request.current) { browserPending.current = false; setBrowserConnecting(false) } }
  }
  return { view, provider, draft: drafts[provider], storedKey: storedKeys[provider], models, error, status,
    saving, cancelling, browserConnecting, update, choose, cancel, startChatGPT, connect, connectBrowser,
    retry: () => retry.current(),
    edit: () => { request.current++; setView(returnView.current); setError('') },
    details: () => setView('details'),
    local: () => setView('local'),
    selectModel: () => { setError(''); setView('models') },
    restore: () => update('baseUrl', presets[provider as keyof typeof presets] || ''),
    reopen: async () => {
      const id = request.current
      try { const result = await window.electronAPI?.chatgpt.reopen(); if (id === request.current && result && !result.ok) setError(t(`chatgpt.errors.${result.code || 'CHATGPT_UNAVAILABLE'}`)) }
      catch { if (id === request.current) setError(t('chatgpt.errors.CHATGPT_UNAVAILABLE')) }
    },
  }
}

type Controller = ReturnType<typeof useOnboardingAdvisor>
const linkClass = 'self-start text-sm leading-5 text-accent-cyan hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-cyan rounded'
export function onboardingAdvisorTitle(controller: Controller, t: (key: string, options?: Record<string, string>) => string) {
  const { view, provider } = controller
  return view === 'choice' || provider === 'chatgpt' || view === 'error' ? t('onboarding.slim.connectAdvisor')
    : ['local', 'models', 'details'].includes(view) && (provider === 'ollama' || provider === 'lm_studio') ? t('onboarding.slim.localModels')
      : provider === 'custom' ? t('onboarding.slim.customEndpoint')
        : t('onboarding.slim.connectProvider', { provider: providerName(provider) })
}
export function OnboardingAdvisorContent({ controller: c, onSkip, onConnectAIApps }: { controller: Controller; onSkip: () => void; onConnectAIApps?: () => void }) {
  const { t } = useTranslation()
  const { view, provider, draft } = c
  const cloud = provider === 'gemini' || provider === 'openrouter'
  const keyField = <Field label={t('onboarding.provider.keyLabel')} id="onboarding-api-key" type="password" value={draft.apiKey}
    placeholder={c.storedKey ? t('onboarding.slim.savedKey') : provider === 'gemini' ? 'AIza...' : 'sk-or-…'} onChange={value => c.update('apiKey', value)} />
  if (view === 'choice') return <div className="flex flex-1 flex-col justify-center gap-6 py-1">
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-accent-cyan/35 bg-accent-cyan/[0.04] p-4">
      <div className="flex min-w-0 items-center gap-4">
        <img src={chatgptLogo} alt="" className="h-9 w-9 shrink-0" />
        <div><div className="flex flex-wrap items-center gap-3"><p className="text-xl font-semibold leading-7">{providerName('chatgpt')}</p>
          <span className="rounded border border-accent-cyan/30 bg-accent-cyan/10 px-2 py-1 font-mono text-xs text-accent-cyan">{t('onboarding.slim.recommended')}</span></div>
          <p className="mt-1 text-sm leading-5 text-text-secondary">{t('onboarding.slim.planHint')}</p></div>
      </div>
      <button type="button" onClick={() => void c.startChatGPT()} className="flex min-h-12 w-full items-center justify-center gap-3 rounded-lg bg-black px-5 py-3 font-sans text-sm font-medium text-white outline-none ring-1 ring-white/20 hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent-cyan min-[700px]:w-[252px]">
        <img src={chatgptLogo} alt="" className="h-5 w-5" />{t('chatgpt.continue')}
      </button>
    </div>
    <p className="text-sm leading-5 text-text-secondary">{t('onboarding.slim.chatgptDisclosure')}</p>
    <div className="space-y-3"><p className="font-mono text-xs leading-4 tracking-widest text-text-secondary uppercase">{t('onboarding.slim.otherOptions')}</p>
      <div className="grid grid-cols-1 gap-3 min-[600px]:grid-cols-3">
        {([['gemini', 'gemini'], ['openrouter', 'openrouter'], ['ollama', 'local']] as const).map(([id, next]) => <button key={id} type="button" onClick={() => c.choose(id, next)}
          className="flex min-h-[76px] min-w-0 items-center gap-3 rounded-lg border border-white/[0.14] bg-bg-tertiary/35 p-3 text-left outline-none hover:border-accent-cyan/50 focus-visible:ring-2 focus-visible:ring-accent-cyan">
          <OnboardingIcon kind={id} className="h-6 w-6 text-text-primary" /><div className="min-w-0"><p className="text-base font-medium leading-6">{id === 'ollama' ? t('onboarding.slim.localModels') : providerName(id)}</p>
            <p className="text-xs leading-4 text-text-secondary">{id === 'ollama' ? t('onboarding.slim.localApps') : t('onboarding.slim.apiKeyHint')}</p></div>
        </button>)}
      </div>
      <div className="flex flex-wrap justify-between gap-3">
        <button type="button" className={`${linkClass} text-text-secondary`} onClick={() => c.choose('custom', 'custom')}>{t('onboarding.slim.customEndpoint')}</button>
        {onConnectAIApps && <button type="button" className={`${linkClass} text-text-secondary`} onClick={onConnectAIApps}>{t('settings.aiSetup.routes.relay.title')}</button>}
      </div>
    </div>
  </div>
  if (view === 'connecting') return <div role="status" aria-live="polite" className="flex flex-1 flex-col items-center justify-center gap-4 py-3 text-center [&_button]:self-center">
    {provider === 'chatgpt' ? <img src={chatgptLogo} alt="" className="h-12 w-12" /> : <OnboardingIcon kind={provider} className="h-12 w-12 text-accent-cyan" />}
    {(provider === 'chatgpt' && c.status?.connecting) || c.browserConnecting ? <><p className="text-xl leading-7">{t('onboarding.slim.browserTitle')}</p><p className="text-sm text-text-secondary">{t('onboarding.slim.browserHint')}</p>
      {provider === 'chatgpt' && <button type="button" onClick={() => void c.reopen()} className={linkClass}>{t('onboarding.slim.reopen')}</button>}</>
      : <p className="flex items-center justify-center gap-3 text-xl leading-7"><OnboardingSpinner />{t('chatgpt.checking')}</p>}
    {c.error && <p role="alert" className="text-sm text-accent-red">{c.error}</p>}
  </div>
  if (view === 'error') return <div className="flex flex-1 flex-col items-center justify-center gap-4 py-3 text-center [&_button]:self-center">
    <OnboardingIcon kind="error" className="h-12 w-12 text-accent-cyan" /><p className="text-xl leading-7">{t('onboarding.slim.connectionError')}</p>
    <p role="alert" className="max-w-lg break-words text-sm leading-5 text-text-secondary">{c.error}</p>
    {provider !== 'chatgpt' && <button type="button" className={linkClass} onClick={c.edit}>{t('onboarding.slim.editDetails')}</button>}
    {c.models.length > 1 && <button type="button" className={linkClass} onClick={c.selectModel}>{t('onboarding.slim.chooseModel')}</button>}
    <button type="button" className={linkClass} onClick={() => void c.cancel().then(onSkip)}>{t('onboarding.actions.setUpLater')}</button>
  </div>
  if (view === 'models') return <div className="flex flex-col gap-4 py-2">
    <p className="text-sm text-text-secondary">{t('onboarding.slim.chooseModel')}</p>
    <div role="radiogroup" aria-label={t('onboarding.slim.chooseModel')} className="grid grid-cols-1 gap-3 min-[600px]:grid-cols-2">
      {c.models.map(model => <label key={model.id} className={`flex min-h-[84px] min-w-0 cursor-pointer items-center gap-3 rounded-lg border p-4 ${draft.model === model.id ? 'border-accent-cyan/50 bg-accent-cyan/[0.06]' : 'border-white/[0.14] bg-bg-tertiary/35'}`}>
        <input type="radio" name="onboarding-model" value={model.id} checked={draft.model === model.id} onChange={() => c.update('model', model.id)} className="shrink-0 accent-accent-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-bg-secondary" />
        <span className="min-w-0 break-words font-mono text-sm">{model.name}</span>
      </label>)}
    </div>
    <button type="button" className={linkClass} onClick={() => void c.connect(provider, 'local')}>{t('onboarding.slim.refreshModels')}</button>
  </div>
  if (view === 'local') return <div className="flex flex-1 flex-col justify-center gap-4 py-2">
    <p className="text-sm text-text-secondary">{t('onboarding.slim.chooseApp')}</p>
    <div role="radiogroup" aria-label={t('onboarding.slim.chooseApp')} className="grid grid-cols-1 gap-3 min-[600px]:grid-cols-2">
      {(['ollama', 'lm_studio'] as const).map(id => <label key={id} className={`flex min-h-[84px] cursor-pointer items-center gap-3 rounded-lg border p-4 ${provider === id ? 'border-accent-cyan/50 bg-accent-cyan/[0.06]' : 'border-white/[0.14] bg-bg-tertiary/35'}`}>
        <input type="radio" name="onboarding-local-app" checked={provider === id} onChange={() => c.choose(id, 'local')} className="accent-accent-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-bg-secondary" />
        <OnboardingIcon kind="chip" /><span className="text-lg">{providerName(id)}</span>
      </label>)}
    </div><button type="button" className={linkClass} onClick={c.details}>{t('onboarding.slim.connectionDetails')}</button>
  </div>
  return <form id="onboarding-provider-form" onSubmit={event => { event.preventDefault(); void c.connect() }} className="flex flex-1 flex-col justify-center gap-4 py-2">
    {cloud ? <>{provider === 'openrouter' && <button type="button" className={linkClass} onClick={() => void c.connectBrowser()}>{t('onboarding.slim.openRouterSignIn')}</button>}{keyField}<button type="button" className={linkClass} onClick={() => void window.electronAPI?.openExternal(provider === 'gemini' ? 'https://aistudio.google.com/apikey' : 'https://openrouter.ai/settings/keys')}>{t('onboarding.provider.generateKey')} ↗</button>
      <p className="text-sm leading-5 text-text-secondary">{t('onboarding.slim.cloudDisclosure', { provider: providerName(provider) })}</p></>
      : <><Field id="onboarding-server-url" label={t('onboarding.slim.serverUrl')} value={draft.baseUrl} placeholder={customUrlHint} onChange={value => c.update('baseUrl', value)} />
        {view === 'custom' && <Field id="onboarding-custom-model" label={t('onboarding.slim.model')} value={draft.model} placeholder={t('onboarding.slim.modelPlaceholder')} onChange={value => c.update('model', value)} />}
        <Field id="onboarding-optional-key" label={t('onboarding.slim.keyOptional')} type="password" value={draft.apiKey} placeholder={c.storedKey ? t('onboarding.slim.savedKey') : t('onboarding.slim.keyOptionalPlaceholder')} onChange={value => c.update('apiKey', value)} />
        {view === 'details' && <button type="button" className={linkClass} onClick={c.restore}>{t('onboarding.slim.restoreDefault')}</button>}</>}
  </form>
}
export function OnboardingAdvisorActions({ controller: c, onBack, onSkip }: { controller: Controller; onBack: () => void; onSkip: () => void }) {
  const { t } = useTranslation()
  const busy = c.saving || c.cancelling
  const skip = async () => { await c.cancel(); onSkip() }
  const back = async () => {
    if (c.view === 'models' && c.provider === 'openrouter') { c.choose('openrouter', 'openrouter'); return }
    if (c.view === 'models' || c.view === 'details') { c.local(); return }
    await c.cancel(); if (c.view === 'choice') onBack()
  }
  const disabled = (c.view === 'gemini' || c.view === 'openrouter') ? !c.draft.apiKey.trim() && !c.storedKey && !c.draft.credentialId
    : c.view === 'custom' ? !c.draft.baseUrl.trim() || !c.draft.model.trim()
      : c.view === 'details' ? !c.draft.baseUrl.trim() : c.view === 'models' ? !c.draft.model : false
  const formView = ['gemini', 'openrouter', 'custom', 'details'].includes(c.view)
  let right: ReactNode
  if (c.view === 'choice' || c.view === 'connecting') right = <HUDButton variant="ghost" disabled={busy} onClick={() => void skip()}>{t('onboarding.actions.setUpLater')}</HUDButton>
  else right = <div className="ml-auto flex flex-wrap justify-end gap-2">
    <HUDButton data-onboarding-primary="true" disabled={busy || disabled} type={formView ? 'submit' : 'button'} form={formView ? 'onboarding-provider-form' : undefined}
      onClick={formView ? undefined : () => c.view === 'error' ? c.retry() : void c.connect()}>
      {c.view === 'error' ? t('chatgpt.tryAgain') : c.view === 'models' ? t('onboarding.slim.useModel') : c.view === 'details' ? t('onboarding.slim.saveAndConnect')
        : c.view === 'gemini' || c.view === 'openrouter' ? t('onboarding.slim.connectProvider', { provider: providerName(c.provider) }) : t('onboarding.slim.connect')}
    </HUDButton>
  </div>
  return <><HUDButton variant="secondary" disabled={busy} onClick={() => void back()}>{c.view === 'connecting' ? t('chatgpt.cancel') : c.view === 'error' ? t('onboarding.slim.chooseProvider') : t('onboarding.actions.back')}</HUDButton>{right}</>
}
function Field({ label, id, value, placeholder, type = 'text', onChange }: { label: string; id: string; value: string; placeholder: string; type?: string; onChange: (value: string) => void }) {
  return <div className="space-y-2"><label htmlFor={id} className="block font-mono text-xs leading-4 tracking-widest uppercase text-text-secondary">{label}</label>
    <input id={id} type={type} value={value} placeholder={placeholder} onChange={event => onChange(event.target.value)} autoComplete="off" spellCheck={false}
      className="h-11 w-full rounded border border-accent-cyan/25 bg-bg-primary px-3 py-2.5 text-sm text-text-primary outline-none placeholder:text-text-secondary/60 focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan" /></div>
}
