import { useEffect, useId } from 'react'
import { useTranslation } from 'react-i18next'
import { useChatGPT, manageChatGPTUsage } from '../hooks/useChatGPT'
import { useToast } from './Toast'

export default function ChatGPTModelPicker({ compact = false, disabled = false }: {
  compact?: boolean
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { status, modelsLoading, modelSaving, catalogError, loadModels, selectModel } = useChatGPT()
  const id = useId()
  useEffect(() => {
    if (status?.ready && !status.models.length) void loadModels()
  }, [status?.ready, status?.account?.id, loadModels])
  if (!status?.ready) return null
  const label = (model: { id: string; name: string }) => {
    if (model.id === status.recommendedModel) return `${model.name} · ${t('chatgpt.recommended')}`
    if (model.id === 'gpt-5.6-luna') return `${model.name} · ${t('chatgpt.lowerUsage')}`
    return model.name
  }
  const primary = status.models.filter(model => model.id === status.recommendedModel || model.id === 'gpt-5.6-luna')
  const other = status.models.filter(model => !primary.includes(model))
  const selected = status.models.find(model => model.id === status.model)
  const selectedLabel = selected ? label(selected) : status.account?.modelName || status.model
  const saving = modelsLoading || modelSaving
  async function change(model: string) {
    if (saving || model === status?.model) return
    const result = await selectModel(model)
    if (result?.ok) showToast({ type: 'success', message: t('chatgpt.modelUpdated'), duration: 1800 })
    else {
      const code = result?.code || 'CHATGPT_UNAVAILABLE'
      showToast({ type: 'error', message: t(`chatgpt.errors.${code}`, { defaultValue: t('chatgpt.errors.CHATGPT_UNAVAILABLE') }),
        duration: 5000, ...(code === 'CHATGPT_LIMIT' ? { action: { label: t('chatgpt.manageUsage'), onClick: () => void manageChatGPTUsage() } } : {}) })
    }
  }
  if (compact && catalogError) {
    const message = t(`chatgpt.errors.${catalogError}`, { defaultValue: t('chatgpt.errors.CHATGPT_UNAVAILABLE') })
    return <div className="min-w-0 flex-1">
      <span className="sr-only" role="alert">{message}</span>
      <button type="button" title={message} aria-label={`${message} ${t('chatgpt.tryAgain')}`} disabled={saving} onClick={() => void loadModels()} className="max-w-full truncate text-accent-yellow underline">{t('chatgpt.tryAgain')}</button>
    </div>
  }
  return <div className={`min-w-0 ${compact ? 'flex-1 max-w-full' : 'space-y-1.5'}`} data-testid="chatgpt-model-picker">
    {!compact && <label htmlFor={id} className="block pl-1 font-display text-[10px] tracking-widest text-text-secondary uppercase">{t('chatgpt.model')}</label>}
    <div className="relative group max-w-full">
      <select id={id} aria-label={t('chatgpt.model')} aria-busy={saving} disabled={disabled || saving || status.connecting || !status.models.length}
        value={status.model} onChange={event => void change(event.target.value)}
        className={compact
          ? 'block w-auto max-w-full appearance-none rounded-sm border border-transparent bg-transparent py-1 pl-1 pr-5 font-mono text-[11px] text-accent-cyan hover:border-accent-cyan/30 focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cyan disabled:opacity-50'
          : 'w-full appearance-none rounded-sm border border-white/10 bg-black/20 px-4 py-2 pr-8 font-mono text-sm text-text-primary focus:outline-none focus:border-accent-cyan/50 focus:bg-accent-cyan/5 disabled:opacity-50'}>
        {!status.models.length && <option value={status.model}>{selectedLabel}</option>}
        {primary.map(model => <option className="bg-bg-tertiary text-text-primary" key={model.id} value={model.id}>{label(model)}</option>)}
        {!!other.length && <optgroup label={t('chatgpt.moreModels')} className="bg-bg-tertiary text-text-secondary">
          {other.map(model => <option key={model.id} value={model.id} className="text-text-primary">{model.name}</option>)}
        </optgroup>}
      </select>
      <svg aria-hidden="true" className={`pointer-events-none absolute top-1/2 -translate-y-1/2 text-accent-cyan/60 ${compact ? 'right-1.5' : 'right-3'}`} width="10" height="6" viewBox="0 0 10 6" fill="none">
        <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
    {catalogError && <div className="mt-1 max-w-sm text-xs text-accent-yellow">
      <p role="alert">{t(`chatgpt.errors.${catalogError}`, { defaultValue: t('chatgpt.errors.CHATGPT_UNAVAILABLE') })}</p>
      <button type="button" disabled={saving} onClick={() => void loadModels()} className="mt-1 underline">{t('chatgpt.tryAgain')}</button>
    </div>}
  </div>
}
