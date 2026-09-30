import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { McpRelayHealthResult, McpRelayStatus } from '../../global'
import { HUDButton } from '../hud/HUDButton'
import { HUDLabel } from '../hud/HUDText'

const clients = ['claude', 'codex', 'cursor'] as const
type Client = typeof clients[number]
type Question = 'priorities' | 'economy' | 'chronicle'

export function MCPRelayPanel({ onChooseCampaign, active = true }: {
  onChooseCampaign?: () => void | Promise<void>
  active?: boolean
}) {
  const { t, i18n } = useTranslation()
  const [status, setStatus] = useState<McpRelayStatus | null>(null)
  const [health, setHealth] = useState<McpRelayHealthResult | null>(null)
  const [client, setClient] = useState<Client>('claude')
  const [question, setQuestion] = useState<Question>('priorities')
  const [checking, setChecking] = useState(true)
  const [busy, setBusy] = useState(false)
  const [setupError, setSetupError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [copyState, setCopyState] = useState<'copied' | 'copyError' | null>(null)
  const selectedOnce = useRef(false)
  const mounted = useRef(false)
  const refreshId = useRef(0)
  const api = window.electronAPI?.mcpRelay

  const refresh = useCallback(async () => {
    if (!api) return
    const id = ++refreshId.current
    setChecking(true)
    setLoadError(null)
    try {
      const [nextStatus, nextHealth] = await Promise.all([api.status(), api.healthCheck()])
      if (!mounted.current || id !== refreshId.current) return
      setStatus(nextStatus)
      setHealth(nextHealth)
      if (!selectedOnce.current) {
        setClient(clients.find(id => nextStatus.clients[id]?.configured) || 'claude')
        selectedOnce.current = true
      }
    } catch (error) {
      if (!mounted.current || id !== refreshId.current) return
      setHealth(null)
      setLoadError(error instanceof Error ? error.message : String(error))
    } finally {
      if (mounted.current && id === refreshId.current) setChecking(false)
    }
  }, [api])

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; refreshId.current += 1 }
  }, [])

  useEffect(() => {
    if (active) void refresh()
  }, [active, refresh, i18n.resolvedLanguage])

  const connect = async (disconnect = false) => {
    if (!api || busy) return
    if (disconnect && !window.confirm(t('settings.mcpRelay.disconnectConfirm', { target: t(`settings.mcpRelay.clients.${client}.name`) }))) return
    setBusy(true)
    setSetupError(null)
    // Discard an earlier status read so it cannot overwrite the connection result.
    refreshId.current += 1
    try {
      const result = await (disconnect ? api.disconnectClient(client) : api.connectClient(client))
      if (!mounted.current) return
      if (result.status) setStatus(result.status)
      if (!result.success || result.warning) setSetupError(result.error || result.warning || t('settings.mcpRelay.installError'))
      await refresh()
    } catch (error) {
      if (mounted.current) setSetupError(error instanceof Error ? error.message : String(error))
    } finally {
      if (mounted.current) setBusy(false)
    }
  }

  const copy = async (text: string | undefined) => {
    if (!text) return
    try {
      const result = await window.electronAPI?.copyToClipboard(text)
      setCopyState(result?.success ? 'copied' : 'copyError')
    } catch { setCopyState('copyError') }
  }

  const current = status?.clients[client]
  const unavailable = current?.available === false
  const target = t(`settings.mcpRelay.clients.${client}.name`)
  const ready = Boolean(health?.serverHealthy && health.campaignReady)
  const connectionError = setupError || current?.error
  const prompt = t(`settings.mcpRelay.questions.${question}.prompt`)
  const diagnostics = {
    server: { healthy: health?.serverHealthy, version: health?.serverVersion, toolCount: health?.toolCount },
    campaign: { ready: health?.campaignReady, date: health?.campaign?.game_date },
    clients: status && Object.fromEntries(Object.entries(status.clients).map(([id, value]) => [id, {
      configured: value.configured, current: value.current, available: value.available, hasError: Boolean(value.error),
    }])),
    language: status?.language,
  }

  return (
    <section id="ai-app-connections" className="space-y-5" aria-label={t('settings.sections.mcpRelay')}>
      <div className="space-y-2">
        <h2 className="font-display text-lg tracking-wider text-accent-cyan">{t('settings.sections.mcpRelay')}</h2>
        <p className="text-sm text-text-primary">{t('settings.mcpRelay.intro')}</p>
        <p className="text-sm leading-relaxed text-text-secondary">{t('settings.mcpRelay.benefits')}</p>
        <p className="text-xs leading-relaxed text-text-secondary">{t('settings.mcpRelay.plan')}</p>
      </div>

      <div role="group" aria-label={t('settings.mcpRelay.chooseApp')} className="space-y-2">
        <HUDLabel>{t('settings.mcpRelay.chooseApp')}</HUDLabel>
        <div className="flex flex-wrap gap-2">
          {clients.map(id => (
            <button key={id} type="button" disabled={busy} aria-pressed={client === id}
              onClick={() => { selectedOnce.current = true; setClient(id); setSetupError(null); setCopyState(null) }}
              className={`rounded border px-3 py-2 text-sm ${client === id ? 'border-accent-cyan bg-accent-cyan/10 text-accent-cyan' : 'border-white/20 text-text-secondary hover:border-white/40'}`}>
              {t(`settings.mcpRelay.clients.${id}.name`)}
            </button>
          ))}
        </div>
        <p className="text-xs leading-relaxed text-text-secondary">{t(`settings.mcpRelay.clients.${client}.description`)}</p>
      </div>

      <ol className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <li className="space-y-2 rounded border border-white/10 bg-white/5 p-4">
          <h3 className="font-display text-sm text-text-primary">1. {t('settings.mcpRelay.chooseCampaign')}</h3>
          <p role="status" className={`text-sm ${ready ? 'text-accent-green' : 'text-text-secondary'}`}>
            {checking ? t('settings.mcpRelay.loadingSummary') : ready
              ? t('settings.mcpRelay.campaignReady', { empire: health?.campaign?.empire_name || t('settings.mcpRelay.unknownEmpire'), date: health?.campaign?.game_date || '—' })
              : health?.serverHealthy ? t('settings.mcpRelay.noCampaign') : t('settings.mcpRelay.checkFailed')}
          </p>
          <div className="flex flex-wrap gap-2">
            {onChooseCampaign && <HUDButton type="button" variant="secondary" onClick={async () => { await onChooseCampaign(); if (mounted.current) void refresh() }}>
              {t(ready ? 'settings.mcpRelay.changeCampaign' : 'settings.mcpRelay.chooseSave')}
            </HUDButton>}
            <HUDButton type="button" variant="ghost" disabled={checking || busy} onClick={() => void refresh()}>
              {t('settings.mcpRelay.checkAgain')}
            </HUDButton>
          </div>
        </li>
        <li className="space-y-3 rounded border border-white/10 bg-white/5 p-4">
          <h3 className="font-display text-sm text-text-primary">2. {t('settings.mcpRelay.addTo', { target })}</h3>
          <p className="text-xs leading-relaxed text-text-secondary">{t('settings.mcpRelay.setupHelp', { target })}</p>
          {current?.current && !connectionError && <p role="status" className="text-sm text-accent-green">{t('settings.mcpRelay.setupAdded')}</p>}
          {unavailable && <p className="text-sm text-accent-yellow">{t('settings.mcpRelay.appMissing', { target })}</p>}
          {connectionError && <p role="alert" className="text-sm text-accent-yellow">{t('settings.mcpRelay.setupFailed', { target })}</p>}
          <div className="flex flex-wrap gap-2">
            {(!current?.current || connectionError) && <HUDButton type="button" disabled={busy || checking || !status || unavailable} onClick={() => void connect()}>
              {busy ? t('settings.mcpRelay.working') : current?.configured ? t('settings.mcpRelay.updateSetup') : t('settings.mcpRelay.addTo', { target })}
            </HUDButton>}
            {current?.configured && <HUDButton type="button" variant="ghost" disabled={busy} onClick={() => void connect(true)}>
              {t('settings.mcpRelay.disconnect')}
            </HUDButton>}
          </div>
        </li>
        <li className="space-y-3 rounded border border-white/10 bg-white/5 p-4 md:col-span-2">
          <h3 className="font-display text-sm text-text-primary">3. {t('settings.mcpRelay.startChatting')}</h3>
          <p className="text-sm leading-relaxed text-text-secondary">{t('settings.mcpRelay.restart', { target })}</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label={t('settings.mcpRelay.firstQuestion')}>
            {(['priorities', 'economy', 'chronicle'] as const).map(id => <button key={id} type="button" aria-pressed={question === id}
              onClick={() => { setQuestion(id); setCopyState(null) }}
              className={`rounded border px-2 py-1 text-xs ${question === id ? 'border-accent-cyan text-accent-cyan' : 'border-white/20 text-text-secondary'}`}>
              {t(`settings.mcpRelay.questions.${id}.label`)}
            </button>)}
          </div>
          <p className="text-sm leading-relaxed text-text-primary">{prompt}</p>
          <HUDButton type="button" variant="secondary" onClick={() => void copy(prompt)}>{t('settings.mcpRelay.copyQuestion')}</HUDButton>
          {question === 'chronicle' && <p className="text-xs text-text-secondary">{t('settings.mcpRelay.chronicleSave')}</p>}
          <p className="text-xs leading-relaxed text-text-secondary">{t('settings.mcpRelay.keepOpen')}</p>
        </li>
      </ol>

      {copyState && <p role="status" className="text-sm text-accent-cyan">{t(`settings.mcpRelay.${copyState}`)}</p>}
      <details className="border-t border-white/10 pt-3">
        <summary className="cursor-pointer text-sm text-text-secondary">{t('settings.mcpRelay.advanced')}</summary>
        <div className="mt-3 space-y-3">
          <p className="text-xs leading-relaxed text-text-secondary">{t(`settings.mcpRelay.manual.${client}`)}</p>
          <HUDButton type="button" variant="secondary" disabled={!status} onClick={() => void copy(client === 'codex' ? status?.snippets.codex : status?.snippets.genericJson)}>
            {t(client === 'codex' ? 'settings.mcpRelay.copyCodexSetup' : 'settings.mcpRelay.copyMcpJson')}
          </HUDButton>
          {client === 'claude' && status?.mcpbPath && <HUDButton type="button" variant="ghost" onClick={async () => {
            const result = await api?.openClaudeExtension()
            if (!result?.success) setSetupError(result?.error || t('settings.mcpRelay.installError'))
          }}>{t('settings.mcpRelay.installClaudeExtension')}</HUDButton>}
          <p className="text-xs text-text-secondary">{t('settings.mcpRelay.otherApps')}</p>
          {client === 'codex' && <HUDButton type="button" variant="ghost" disabled={!status} onClick={() => void copy(status?.snippets.genericJson)}>{t('settings.mcpRelay.copyMcpJson')}</HUDButton>}
          <div className="space-y-2 border-t border-white/10 pt-3">
            <HUDLabel>{t('settings.mcpRelay.diagnostics')}</HUDLabel>
            {(connectionError || loadError || (health && !health.serverHealthy)) && <p className="break-all font-mono text-xs text-accent-yellow">{connectionError || loadError || health?.message}</p>}
            <div className="flex flex-wrap gap-2">
              <HUDButton type="button" variant="secondary" disabled={!status && !health} onClick={() => void copy(JSON.stringify(diagnostics, null, 2))}>{t('settings.mcpRelay.copyDiagnostics')}</HUDButton>
              <HUDButton type="button" variant="ghost" disabled={!status?.logPath} onClick={() => status?.logPath && void api?.revealPath(status.logPath)}>{t('settings.mcpRelay.revealLog')}</HUDButton>
            </div>
          </div>
        </div>
      </details>
    </section>
  )
}
