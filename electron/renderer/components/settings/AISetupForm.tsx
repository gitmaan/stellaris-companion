import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AdvisorProvider, Settings } from '../../hooks/useSettings'
import { HUDButton } from '../hud/HUDButton'
import { HUDInput } from '../hud/HUDInput'
import { HUDSelect } from '../hud/HUDForm'
import { HUDMicro } from '../hud/HUDText'
import { AdvisorProviderChooser } from './AdvisorProviderChooser'
import ChatGPTConnection from '../ChatGPTConnection'

export type AISetupValues = Pick<
  Settings,
  | 'advisorProvider'
  | 'advisorModel'
  | 'advisorBaseUrl'
  | 'googleApiKey'
  | 'openRouterApiKey'
  | 'customProviderApiKey'
> & { openRouterCredentialId?: string }
interface Model {
  id: string
  name: string
  recommended?: boolean
  contextLength?: number
  pricing?: { inputPerMillion: number; outputPerMillion: number }
}
interface CheckResult {
  ok: boolean
  errorCode?: string
  error?: string
  status?: number
  chronicleReady?: boolean
}
interface Props {
  initialSettings?: Partial<Settings> | null
  onSave: (values: Partial<AISetupValues>) => Promise<boolean>
  onSaved?: () => void
  onProviderChange?: (provider: AdvisorProvider) => void
  onChatGPTActivated?: () => Promise<void>
}

function initialValues(settings?: Partial<Settings> | null): AISetupValues {
  return {
    advisorProvider: settings?.advisorProvider || 'gemini',
    advisorModel: settings?.advisorModel || '',
    advisorBaseUrl: settings?.advisorBaseUrl || '',
    googleApiKey: settings?.googleApiKey || '',
    openRouterApiKey: settings?.openRouterApiKey || '',
    customProviderApiKey: settings?.customProviderApiKey || '',
  }
}
const names: Record<AdvisorProvider, string> = {
  chatgpt: 'ChatGPT',
  gemini: 'Gemini',
  openrouter: 'OpenRouter',
  ollama: 'Ollama',
  lm_studio: 'LM Studio',
  custom: 'Custom',
}
const errorKeys: Record<string, string> = {
  PROVIDER_AUTH_FAILED: 'providerAuthFailed',
  PROVIDER_MODEL_NOT_FOUND: 'providerModelNotFound',
  PROVIDER_UNAVAILABLE: 'providerUnavailable',
  PROVIDER_TIMEOUT: 'providerTimeout',
  PROVIDER_RATE_LIMITED: 'providerRateLimited',
  PROVIDER_BILLING_FAILED: 'providerBillingFailed',
  PROVIDER_CONTEXT_LIMIT: 'providerContextLimit',
  PROVIDER_EMPTY_RESPONSE: 'providerEmptyResponse',
  PROVIDER_REQUEST_FAILED: 'providerRequestFailed',
}

export function AISetupForm({
  initialSettings,
  onSave,
  onSaved,
  onProviderChange,
  onChatGPTActivated,
}: Props) {
  const { t, i18n } = useTranslation()
  const [values, setValues] = useState(() => initialValues(initialSettings))
  const [models, setModels] = useState<Model[]>([])
  const [allModels, setAllModels] = useState(false)
  const [search, setSearch] = useState('')
  const [manualKey, setManualKey] = useState(false)
  const [busy, setBusy] = useState<'models' | 'check' | 'browser' | null>(null)
  const [result, setResult] = useState<CheckResult | null>(null)
  const [notice, setNotice] = useState('')
  const request = useRef(0)
  const mounted = useRef(true)
  const browserPending = useRef(false)
  const provider = values.advisorProvider
  const isLocal = provider === 'ollama' || provider === 'lm_studio'
  const keyField =
    provider === 'gemini'
      ? 'googleApiKey'
      : provider === 'openrouter'
        ? 'openRouterApiKey'
        : 'customProviderApiKey'
  const apiKey = isLocal ? '' : values[keyField]
  const hasKey = Boolean(
    apiKey.trim() || (provider === 'openrouter' && values.openRouterCredentialId)
  )
  const api = window.electronAPI?.advisorProviders

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      request.current += 1
      if (browserPending.current) void window.electronAPI?.advisorProviders.cancelOpenRouter()
    }
  }, [])

  const change = (next: Partial<AISetupValues>) => {
    request.current += 1
    setResult(null)
    setNotice('')
    if (
      next.advisorProvider ||
      next.advisorBaseUrl !== undefined ||
      next.openRouterApiKey !== undefined ||
      next.customProviderApiKey !== undefined
    )
      setModels([])
    if (next.advisorProvider && next.advisorProvider !== provider) {
      next.advisorModel = ''
      next.advisorBaseUrl = ''
      setAllModels(false)
      setSearch('')
      onProviderChange?.(next.advisorProvider)
    }
    if (
      next.openRouterApiKey !== undefined ||
      (next.advisorProvider && next.advisorProvider !== provider)
    ) {
      next.openRouterCredentialId = undefined
      if (browserPending.current) {
        void api?.cancelOpenRouter()
        browserPending.current = false
      }
    }
    setValues((current) => ({ ...current, ...next }))
  }

  const config = (draft = values) => ({
    provider: draft.advisorProvider,
    baseUrl: draft.advisorBaseUrl,
    model: draft.advisorModel,
    apiKey:
      draft.advisorProvider === 'gemini'
        ? draft.googleApiKey
        : draft.advisorProvider === 'openrouter'
          ? draft.openRouterApiKey
          : draft.advisorProvider === 'custom'
            ? draft.customProviderApiKey
            : '',
    credentialId: draft.advisorProvider === 'openrouter' ? draft.openRouterCredentialId : undefined,
  })

  const findModels = async (draft = values) => {
    if (!api) return
    const id = ++request.current
    setBusy('models')
    setResult(null)
    setNotice('')
    try {
      const found = await api.listModels(config(draft))
      if (!mounted.current || id !== request.current) return
      if (!found.ok) {
        setResult(found)
        return
      }
      const available = found.models || []
      setModels(available)
      // Make the low-cost default explicit before the user checks and saves it.
      const suggested =
        available.find((model) => model.id === 'google/gemini-3.1-flash-lite') ||
        available.find((model) => model.recommended) ||
        (available.length === 1 ? available[0] : null)
      if (suggested && !draft.advisorModel)
        setValues((current) => ({ ...current, advisorModel: suggested.id }))
      setNotice(available.length ? 'chooseModel' : 'noModels')
    } catch {
      if (mounted.current && id === request.current)
        setResult({ ok: false, errorCode: 'PROVIDER_UNAVAILABLE' })
    } finally {
      if (mounted.current && id === request.current) setBusy(null)
    }
  }

  const connectBrowser = async () => {
    if (!api) return
    const id = ++request.current
    browserPending.current = true
    setBusy('browser')
    setResult(null)
    setNotice('')
    try {
      const connected = await api.connectOpenRouter()
      if (!mounted.current || id !== request.current) return
      if (!connected.ok) {
        browserPending.current = false
        setResult(connected)
        return
      }
      const draft = {
        ...values,
        openRouterCredentialId: connected.credentialId,
        openRouterApiKey: '',
      }
      setValues(draft)
      await findModels(draft)
    } catch {
      if (mounted.current && id === request.current)
        setResult({ ok: false, errorCode: 'CONNECTION_FAILED' })
    } finally {
      if (mounted.current && id === request.current) setBusy(null)
    }
  }

  const cancelBrowser = () => {
    request.current += 1
    browserPending.current = false
    void api?.cancelOpenRouter()
    setBusy(null)
    setResult({ ok: false, errorCode: 'CONNECTION_CANCELLED' })
  }

  const checkAndSave = async () => {
    if (!api) return
    if (provider !== 'gemini' && !values.advisorModel.trim()) {
      await findModels()
      return
    }
    const id = ++request.current
    setBusy('check')
    setResult(null)
    setNotice('')
    try {
      const checked = await api.testModel(config())
      if (!mounted.current || id !== request.current) return
      if (!checked.ok) {
        setResult(checked)
        return
      }
      const saved = await onSave({
        ...values,
        advisorModel: provider === 'gemini' ? '' : values.advisorModel.trim(),
      })
      if (!mounted.current || id !== request.current) return
      if (!saved) {
        setResult({ ok: false, errorCode: 'SAVE_FAILED' })
        return
      }
      browserPending.current = false
      const settings = (await window.electronAPI?.getSettings()) as Settings
      if (!mounted.current || id !== request.current) return
      setValues(initialValues(settings))
      setResult(checked)
      onSaved?.()
    } catch {
      if (mounted.current && id === request.current)
        setResult({ ok: false, errorCode: 'SAVE_FAILED' })
    } finally {
      if (mounted.current && id === request.current) setBusy(null)
    }
  }

  const removeSavedKey = async () => {
    const id = ++request.current
    setBusy('check')
    setResult(null)
    setNotice('')
    try {
      const saved = await onSave({ [keyField]: '' })
      if (!mounted.current || id !== request.current) return
      if (!saved) {
        setResult({ ok: false, errorCode: 'SAVE_FAILED' })
        return
      }
      if (browserPending.current) {
        void api?.cancelOpenRouter()
        browserPending.current = false
      }
      setValues((current) => ({ ...current, [keyField]: '', openRouterCredentialId: undefined }))
      setNotice('keyRemoved')
    } catch {
      if (mounted.current && id === request.current)
        setResult({ ok: false, errorCode: 'SAVE_FAILED' })
    } finally {
      if (mounted.current && id === request.current) setBusy(null)
    }
  }

  const recommended = models.filter((model) => model.recommended)
  const pool = provider === 'openrouter' && !allModels && recommended.length ? recommended : models
  const filtered = pool
    .filter((model) => `${model.name} ${model.id}`.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 200)
  const selected = models.find((model) => model.id === values.advisorModel)
  const choices = selected && !filtered.includes(selected) ? [selected, ...filtered] : filtered
  const modelOptions = [
    { value: '', label: t('settings.advisor.selectModel') },
    ...choices.map((model) => ({ value: model.id, label: model.name })),
  ]
  if (values.advisorModel && !modelOptions.some((option) => option.value === values.advisorModel))
    modelOptions.push({ value: values.advisorModel, label: values.advisorModel })
  const billingUrl =
    provider === 'gemini'
      ? 'https://aistudio.google.com/usage'
      : provider === 'openrouter'
        ? 'https://openrouter.ai/credits'
        : null
  const requiresKey = provider === 'gemini' || provider === 'openrouter'
  const missingRequired =
    (requiresKey && !hasKey) || (provider === 'custom' && !values.advisorBaseUrl.trim())
  const errorKey = errorKeys[result?.errorCode || ''] || 'providerRequestFailed'
  const oauthError = result?.errorCode?.startsWith('CONNECTION_')
  const unitPrice = (value: number) =>
    new Intl.NumberFormat(i18n.language, {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 3,
    }).format(value)

  return (
    <div className="space-y-4" data-testid="ai-setup-form">
      <fieldset disabled={Boolean(busy)} className="min-w-0 space-y-4 disabled:opacity-70">
        <AdvisorProviderChooser
          provider={provider}
          onChange={(advisorProvider) => change({ advisorProvider })}
        />
        {provider === 'chatgpt' ? <ChatGPTConnection active={initialSettings?.advisorProvider === 'chatgpt'} onActivated={async status => {
          setValues(current => ({ ...current, advisorModel: status.model, advisorBaseUrl: '' }))
          await onChatGPTActivated?.()
          onSaved?.()
        }} /> : <>
        <p className="text-sm leading-relaxed text-text-secondary">
          {t(`settings.aiSetup.help.${provider}`)}
        </p>
        {provider === 'gemini' && (
          <>
            <HUDInput
              label={t('onboarding.ai.geminiKey')}
              type="password"
              autoComplete="off"
              value={values.googleApiKey}
              onChange={(event) => change({ googleApiKey: event.target.value })}
              placeholder="AIza…"
            />
            <a
              className="inline-block text-sm text-accent-cyan underline"
              href="https://aistudio.google.com/app/apikey"
              target="_blank"
              rel="noreferrer"
            >
              {t('onboarding.ai.getGeminiKey')}
            </a>
          </>
        )}
        {provider === 'openrouter' && (
          <>
            <HUDButton
              type="button"
              variant={hasKey ? 'secondary' : 'primary'}
              onClick={() => void connectBrowser()}
            >
              {t('settings.aiSetup.connectOpenRouter')}
            </HUDButton>
            {values.openRouterCredentialId && (
              <p className="text-sm text-text-secondary">{t('settings.aiSetup.accountEntered')}</p>
            )}
            <details
              open={manualKey || undefined}
              onToggle={(event) => setManualKey(event.currentTarget.open)}
            >
              <summary className="cursor-pointer text-sm text-text-secondary">
                {t('settings.aiSetup.manualKey')}
              </summary>
              <div className="mt-3">
                <HUDInput
                  label={t('settings.advisor.apiKeyLabel')}
                  type="password"
                  autoComplete="off"
                  value={values.openRouterApiKey}
                  onChange={(event) => change({ openRouterApiKey: event.target.value })}
                />
              </div>
            </details>
          </>
        )}
        {provider === 'custom' && (
          <>
            <HUDInput
              label={t('settings.advisor.baseUrlLabel')}
              value={values.advisorBaseUrl}
              onChange={(event) => change({ advisorBaseUrl: event.target.value })}
              placeholder="https://provider.example/v1"
            />
            <HUDInput
              label={t('settings.advisor.optionalApiKeyLabel')}
              type="password"
              autoComplete="off"
              value={values.customProviderApiKey}
              onChange={(event) => change({ customProviderApiKey: event.target.value })}
              placeholder={t('settings.advisor.optional')}
            />
          </>
        )}
        {provider !== 'gemini' && (models.length > 0 || values.advisorModel) && (
          <div className="space-y-3">
            {provider === 'openrouter' && recommended.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setAllModels(!allModels)
                  setSearch('')
                }}
                className="text-sm text-accent-cyan underline"
              >
                {t(
                  allModels
                    ? 'settings.advisor.showRecommendedModels'
                    : 'settings.advisor.showAllModels'
                )}
              </button>
            )}
            {(allModels || !recommended.length) && models.length > 8 && (
              <HUDInput
                label={t('settings.advisor.searchModels')}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t('settings.aiSetup.searchPlaceholder')}
              />
            )}
            <HUDSelect
              label={t('settings.advisor.modelLabel')}
              value={values.advisorModel}
              options={modelOptions}
              onChange={(event) => change({ advisorModel: event.target.value })}
            />
            {selected?.pricing && (
              <p className="text-sm text-text-secondary">
                {t(
                  selected.pricing.inputPerMillion === 0 && selected.pricing.outputPerMillion === 0
                    ? 'settings.aiSetup.freeModel'
                    : selected.pricing.inputPerMillion <= 1 &&
                        selected.pricing.outputPerMillion <= 2
                      ? 'settings.aiSetup.lowerCost'
                      : 'settings.aiSetup.paidModel'
                )}
              </p>
            )}
          </div>
        )}
        {provider !== 'gemini' && (
          <details className="border-t border-white/10 pt-3">
            <summary className="cursor-pointer text-sm text-text-secondary">
              {t('settings.aiSetup.advanced')}
            </summary>
            <div className="mt-3 space-y-3">
              {isLocal && (
                <HUDInput
                  label={t('settings.advisor.baseUrlLabel')}
                  value={values.advisorBaseUrl}
                  onChange={(event) => change({ advisorBaseUrl: event.target.value })}
                  placeholder={
                    provider === 'ollama' ? 'http://127.0.0.1:11434/v1' : 'http://127.0.0.1:1234/v1'
                  }
                />
              )}
              <HUDInput
                label={t('settings.aiSetup.modelId')}
                value={values.advisorModel}
                onChange={(event) => change({ advisorModel: event.target.value })}
              />
              <HUDButton
                type="button"
                variant="secondary"
                disabled={missingRequired}
                onClick={() => void findModels()}
              >
                {t('settings.aiSetup.refreshModels')}
              </HUDButton>
              {selected?.contextLength && (
                <p className="text-sm text-text-secondary">
                  {t('settings.advisor.modelContextDetected', {
                    context: selected.contextLength.toLocaleString(i18n.language),
                  })}
                </p>
              )}
              {selected?.pricing && (
                <p className="text-sm text-text-secondary">
                  {t('settings.aiSetup.prices', {
                    input: unitPrice(selected.pricing.inputPerMillion),
                    output: unitPrice(selected.pricing.outputPerMillion),
                  })}
                </p>
              )}
            </div>
          </details>
        )}
        {selected?.contextLength && selected.contextLength < 32768 && (
          <p className="text-sm text-accent-yellow">{t('settings.aiSetup.smallModel')}</p>
        )}
        {isLocal && (
          <a
            className="inline-block text-sm text-accent-cyan underline"
            href={
              provider === 'ollama'
                ? 'https://docs.ollama.com/quickstart'
                : 'https://lmstudio.ai/docs/developer/core/server'
            }
            target="_blank"
            rel="noreferrer"
          >
            {t('settings.aiSetup.localHelp')}
          </a>
        )}
        {(provider === 'openrouter' ||
          provider === 'custom' ||
          provider === 'gemini' ||
          values.advisorModel.includes(':cloud')) && (
          <p className="text-xs leading-relaxed text-text-secondary">
            {t('settings.advisor.remoteContextNotice')}
          </p>
        )}
        {billingUrl && (
          <p className="text-xs leading-relaxed text-text-secondary">
            {t('settings.aiSetup.billing')}{' '}
            <a
              className="text-accent-cyan underline"
              href={billingUrl}
              target="_blank"
              rel="noreferrer"
            >
              {t('settings.aiSetup.manageUsage')}
            </a>
          </p>
        )}
        </>}
      </fieldset>
      {busy === 'browser' ? (
        <div className="space-y-2" role="status">
          <p className="text-sm text-text-secondary">{t('settings.aiSetup.browserWaiting')}</p>
          <HUDButton type="button" variant="secondary" onClick={cancelBrowser}>
            {t('common.cancel')}
          </HUDButton>
        </div>
      ) : (
        <>
          <HUDButton
            type="button"
            variant="primary"
            disabled={Boolean(busy) || missingRequired}
            onClick={() => void checkAndSave()}
          >
            {t(
              busy
                ? 'settings.aiSetup.checking'
                : provider !== 'gemini' && !values.advisorModel
                  ? 'settings.aiSetup.findModels'
                  : 'settings.aiSetup.checkSave'
            )}
          </HUDButton>
          <HUDMicro className="block normal-case leading-relaxed">
            {t('settings.aiSetup.testNotice')}
          </HUDMicro>
        </>
      )}
      {notice && (
        <p role="status" className="text-sm text-text-secondary">
          {t(`settings.aiSetup.${notice}`)}
        </p>
      )}
      {result && (
        <div
          role={result.ok ? 'status' : 'alert'}
          className={`space-y-2 text-sm ${result.ok ? 'text-accent-green' : 'text-accent-yellow'}`}
        >
          <p>
            {result.ok
              ? t(
                  result.chronicleReady === false
                    ? 'settings.aiSetup.advisorOnly'
                    : 'settings.aiSetup.verified'
                )
              : result.errorCode === 'SAVE_FAILED'
                ? t('settings.aiSetup.saveFailed')
                : oauthError
                  ? t(
                      `settings.aiSetup.${result.errorCode === 'CONNECTION_CANCELLED' ? 'cancelled' : result.errorCode === 'CONNECTION_TIMEOUT' ? 'browserTimeout' : 'browserFailed'}`
                    )
                  : t(`chat.errors.${errorKey}`, { provider: names[provider] })}
          </p>
          {!result.ok && result.error && (
            <details>
              <summary className="cursor-pointer">{t('settings.aiSetup.details')}</summary>
              <p className="mt-1 break-words font-mono text-xs">{result.error}</p>
            </details>
          )}
          {!result.ok && (
            <button
              type="button"
              className="underline"
              onClick={async () => {
                const version = await window.electronAPI?.getAppVersion()
                await window.electronAPI?.copyToClipboard(
                  JSON.stringify(
                    {
                      version,
                      provider,
                      model: values.advisorModel || 'Gemini default',
                      error: result.errorCode,
                      status: result.status,
                    },
                    null,
                    2
                  )
                )
              }}
            >
              {t('settings.aiSetup.copyDetails')}
            </button>
          )}
        </div>
      )}
      {provider !== 'chatgpt' && !isLocal && (initialSettings?.[`${keyField}Set`] || apiKey.includes('...')) && (
        <button
          type="button"
          disabled={Boolean(busy)}
          className="block text-sm text-text-secondary underline"
          onClick={() => void removeSavedKey()}
        >
          {t('settings.aiSetup.removeKey')}
        </button>
      )}

    </div>
  )
}
