import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useChatGPT, manageChatGPTUsage } from '../hooks/useChatGPT'
import type { ChatGPTResult, ChatGPTStatus } from '../global'
import logo from '../assets/chatgpt-logo-white.svg'
import ChatGPTModelPicker from './ChatGPTModelPicker'

export default function ChatGPTConnection({ onActivated, compact = false, active = true }: {
  onActivated?: (status: ChatGPTStatus) => void | Promise<void>
  compact?: boolean
  active?: boolean
}) {
  const { t } = useTranslation()
  const { status, accept } = useChatGPT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState(false)
  const connected = status?.connected
  const ready = status?.ready
  async function run(operation: () => Promise<ChatGPTResult>, activates = true) {
    setBusy(true); setError(null); setNotice(false)
    try {
      const result = accept(await operation())
      if (!result.ok) setError(result.code || 'CHATGPT_UNAVAILABLE')
      else {
        if (activates && result.status.ready) await onActivated?.(result.status)
        if (result.status.revocationConfirmed === false) setNotice(true)
      }
    } catch { setError('CHATGPT_UNAVAILABLE') }
    finally { setBusy(false) }
  }
  const api = window.electronAPI?.chatgpt
  if (!api) return null
  return (
    <div className="rounded-xl border border-white/15 bg-black/25 p-5 space-y-4" data-testid="chatgpt-connection">
      <div className="flex items-start gap-3">
        <img src={logo} alt="" className="w-7 h-7 shrink-0 mt-0.5" />
        <div className="min-w-0 space-y-1">
          <h2 className="text-base font-medium text-white">{t(ready ? 'chatgpt.connected' : 'chatgpt.title')}</h2>
          {!ready && <p className="text-sm text-text-secondary leading-relaxed">{t('chatgpt.description')}</p>}
        </div>
      </div>
      {ready && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span className="inline-flex items-center gap-2 text-accent-green"><span className="h-1.5 w-1.5 rounded-full bg-accent-green" />{status?.account?.email || status?.account?.name || t('chatgpt.account')}</span>
          {compact && <span className="text-text-secondary">{status?.models.find(model => model.id === status.model)?.name || status?.account?.modelName || status?.model}</span>}
        </div>
      )}
      {!compact && ready && <ChatGPTModelPicker disabled={busy} />}
      <div className="flex flex-wrap items-center gap-3">
        {!ready && !busy && (
          <button type="button" onClick={() => void run(() => api.connect())}
            className="inline-flex items-center justify-center gap-3 rounded-lg bg-black border border-white/25 px-5 py-3 text-sm font-medium text-white hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent-cyan">
            <img src={logo} alt="" className="w-5 h-5" />{t('chatgpt.continue')}
          </button>
        )}
        {busy && <p role="status" className="text-sm text-accent-cyan animate-pulse">{t(status?.connecting ? 'chatgpt.browser' : 'chatgpt.checking')}</p>}
        {busy && status?.connecting && <button type="button" className="text-sm underline text-text-secondary" onClick={() => void api.cancel()}>{t('chatgpt.cancel')}</button>}
        {ready && !active && <button type="button" disabled={busy} onClick={() => void run(() => api.check())} className="text-sm text-accent-cyan underline">{t('chatgpt.activate')}</button>}
        {connected && <button type="button" onClick={() => void manageChatGPTUsage()} className="text-sm text-accent-cyan hover:underline">{t('chatgpt.manageUsage')}</button>}
      </div>
      {error && <div role="alert" className="space-y-2 text-sm text-accent-yellow">
        <p>{t(`chatgpt.errors.${error}`, { defaultValue: t('chatgpt.errors.CHATGPT_UNAVAILABLE') })}</p>
        {error === 'CHATGPT_LIMIT' && <button type="button" onClick={() => void manageChatGPTUsage()} className="rounded-lg bg-white text-black px-4 py-2 font-medium">{t('chatgpt.manageUsage')}</button>}
        {connected && !ready && <button type="button" disabled={busy} onClick={() => void run(() => api.check())} className="underline">{t('chatgpt.tryAgain')}</button>}
      </div>}
      {notice && <p role="status" className="text-sm text-accent-yellow">{t('chatgpt.disconnectedOffline')}</p>}
      {!ready && <p className="text-xs text-text-secondary leading-relaxed">{t('chatgpt.privacy')}</p>}
      {!compact && (connected || !!status?.accounts.length) && <details className="border-t border-white/10 pt-3">
        <summary className="cursor-pointer text-xs text-text-secondary hover:text-white">{t('chatgpt.advanced')}</summary>
        <div className="pt-4 space-y-3 text-sm">
          {!!status?.accounts.length && <label className="block text-text-secondary">{t('chatgpt.account')}
            <select aria-label={t('chatgpt.account')} disabled={busy} value={status.account?.id || ''}
              onChange={event => void run(() => api.selectAccount(event.target.value))}
              className="block mt-1 w-full rounded-lg border border-white/15 bg-bg-primary px-3 py-2 text-white">
              {status.accounts.map(account => <option key={account.id} value={account.id}>{account.email || account.name || t('chatgpt.account')}</option>)}
            </select>
          </label>}
          <div className="flex flex-wrap gap-4">
            <button type="button" disabled={busy} onClick={() => void run(() => api.connect({ newAccount: true }))} className="text-accent-cyan hover:underline">{t('chatgpt.addAccount')}</button>
            <button type="button" disabled={busy} onClick={() => void run(() => api.check())} className="text-text-secondary hover:underline">{t('chatgpt.checkConnection')}</button>
            <button type="button" disabled={busy} onClick={() => void run(() => api.disconnect(), false)} className="text-text-secondary hover:underline">{t('chatgpt.disconnect')}</button>
          </div>
        </div>
      </details>}
    </div>
  )
}
