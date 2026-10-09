import { useEffect, useState } from 'react'
import Modal from './Modal'
import { HUDButton } from './hud/HUDButton'
import { HUDSelect, HUDCheckbox } from './hud/HUDForm'
import { HUDTextArea } from './hud/HUDInput'
import type { WarDiagnostics } from '../hooks/useBackend'
import { useTranslation } from 'react-i18next'

interface ReportContext {
  appVersion: string
  platform: string
  electronVersion: string
  empireName?: string
  empireEthics?: string[]
  empireCivics?: string[]
  empireOrigin?: string
  empireType?: string
  gameYear?: string
  stellarisVersion?: string
  dlcs?: string[]
  saveFileSizeMb?: number
  galaxySize?: string
  ingestionStage?: string
  ingestionStageDetail?: string
  ingestionLastError?: string
  precomputeReady?: boolean
  t2Ready?: boolean
  warDiagnostics?: WarDiagnostics
  error?: {
    message: string
    stack?: string
    source: string
  }
  llm?: {
    lastPrompt?: string
    lastResponse?: string
    recentTurns?: Array<{ role: 'user' | 'assistant'; content: string }>
    responseTimeMs?: number
    model?: string
  }
}

interface ReportIssueModalProps {
  isOpen: boolean
  onClose: () => void
  prefill?: {
    category?: string
    error?: ReportContext['error']
    llm?: ReportContext['llm']
  }
}

const CATEGORIES = ['Bug', 'Strange LLM Response', 'Missing Content', 'Suggestion', 'Other'] as const
const ISSUE_URL = import.meta.env.VITE_ISSUES_URL || 'https://github.com/gitmaan/stellaris-companion/issues/new'
const REPORT_ENDPOINT = import.meta.env.VITE_REPORT_ENDPOINT || ''

export default function ReportIssueModal({ isOpen, onClose, prefill }: ReportIssueModalProps) {
  const { t } = useTranslation()
  const [category, setCategory] = useState(prefill?.category || '')
  const [description, setDescription] = useState('')
  const [context, setContext] = useState<ReportContext | null>(null)

  // Opt-in toggles (default off)
  const [includeDiagnostics, setIncludeDiagnostics] = useState(false)
  const [includeBackendLogs, setIncludeBackendLogs] = useState(false)
  const [includeScreenshot, setIncludeScreenshot] = useState(false)
  const [includeErrorContext, setIncludeErrorContext] = useState(false)
  const [includeLlmContext, setIncludeLlmContext] = useState(false)

  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    ;(async () => {
      const info = window.electronAPI?.getPlatformInfo?.()
      const platform = info ? `${info.platform}-${info.arch}` : navigator.platform
      const ctx: ReportContext = {
        appVersion: await window.electronAPI?.getAppVersion?.() || 'unknown',
        platform,
        electronVersion: navigator.userAgent.match(/Electron\/([\d.]+)/)?.[1] || 'unknown',
      }
      setContext(ctx)
    })().catch(() => setContext(null))

    const initial = prefill?.category || ''
    setCategory(initial)
    setDescription('')
    setIncludeDiagnostics(false)
    setIncludeBackendLogs(false)
    setIncludeScreenshot(false)
    setIncludeErrorContext(false)
    setIncludeLlmContext(false)
    setStatus(null)
  }, [isOpen, prefill])

  async function enrichContext(base: ReportContext): Promise<ReportContext> {
    const ctx: ReportContext = { ...base }

    if (includeDiagnostics) {
      try {
        const diagnosticsResp = await window.electronAPI?.backend?.diagnostics()
        if (diagnosticsResp && typeof diagnosticsResp === 'object' && 'ok' in diagnosticsResp && diagnosticsResp.ok) {
          const diagnostics = diagnosticsResp.data
          ctx.empireName = diagnostics.empireName || undefined
          ctx.empireEthics = diagnostics.empireEthics?.length ? diagnostics.empireEthics : undefined
          ctx.empireCivics = diagnostics.empireCivics?.length ? diagnostics.empireCivics : undefined
          ctx.empireOrigin = diagnostics.empireOrigin || undefined
          ctx.empireType = diagnostics.empireType || undefined
          ctx.gameYear = diagnostics.gameYear || undefined
          ctx.stellarisVersion = diagnostics.stellarisVersion || undefined
          ctx.dlcs = diagnostics.dlcs?.length ? diagnostics.dlcs : undefined
          ctx.saveFileSizeMb = diagnostics.saveFileSizeMb || undefined
          ctx.galaxySize = diagnostics.galaxySize || undefined
          ctx.ingestionStage = diagnostics.ingestionStage || undefined
          ctx.ingestionStageDetail = diagnostics.ingestionStageDetail || undefined
          ctx.ingestionLastError = diagnostics.ingestionLastError || undefined
          ctx.precomputeReady = typeof diagnostics.precomputeReady === 'boolean' ? diagnostics.precomputeReady : undefined
          ctx.t2Ready = typeof diagnostics.t2Ready === 'boolean' ? diagnostics.t2Ready : undefined
          ctx.warDiagnostics = diagnostics.warDiagnostics || undefined
        } else {
          throw new Error('Diagnostics unavailable')
        }
      } catch {
        try {
          const healthResp = await window.electronAPI?.backend?.health()
          if (healthResp && typeof healthResp === 'object' && 'ok' in healthResp && healthResp.ok) {
            const health = healthResp.data
            ctx.empireName = health.empire_name || undefined
            ctx.gameYear = health.game_date || undefined
          }
        } catch {
          // ignore
        }
      }
    }

    if (includeErrorContext && prefill?.error) ctx.error = prefill.error
    if (includeLlmContext && prefill?.llm) ctx.llm = prefill.llm

    return ctx
  }

  function formatReportMarkdown(ctx: ReportContext, backendLogTail?: string): string {
    const lines: string[] = []
    const field = (key: string, value: string | number | boolean) =>
      `- ${t(`report.markdown.fields.${key}`, { value })}`

    lines.push(`# ${category ? t(`report.categories.${category}`) : t('report.markdown.report')}`)
    lines.push('')
    lines.push(`## ${t('report.markdown.whatHappened')}`)
    lines.push(description.trim() || t('report.markdown.fillIn'))
    lines.push('')
    lines.push(`## ${t('report.markdown.environment')}`)
    lines.push(field('appVersion', ctx.appVersion))
    lines.push(field('platform', ctx.platform))
    lines.push(field('electronVersion', ctx.electronVersion))
    lines.push('')

    if (includeDiagnostics) {
      lines.push(`## ${t('report.markdown.gameContext')}`)
      if (ctx.stellarisVersion) lines.push(field('stellarisVersion', ctx.stellarisVersion))
      if (typeof ctx.saveFileSizeMb === 'number') lines.push(field('saveSize', ctx.saveFileSizeMb))
      if (ctx.galaxySize) lines.push(field('galaxySize', ctx.galaxySize))
      if (ctx.gameYear) lines.push(field('gameYear', ctx.gameYear))
      if (ctx.ingestionStage) lines.push(field('ingestionStage', ctx.ingestionStage))
      if (ctx.ingestionStageDetail) lines.push(field('ingestionDetail', ctx.ingestionStageDetail))
      if (typeof ctx.precomputeReady === 'boolean') lines.push(field('precomputeReady', ctx.precomputeReady))
      if (typeof ctx.t2Ready === 'boolean') lines.push(field('t2Ready', ctx.t2Ready))
      if (ctx.empireName) lines.push(field('empire', ctx.empireName))
      if (ctx.empireType) lines.push(field('empireType', ctx.empireType))
      if (ctx.empireOrigin) lines.push(field('origin', ctx.empireOrigin))
      if (ctx.empireEthics?.length) lines.push(field('ethics', ctx.empireEthics.join(', ')))
      if (ctx.empireCivics?.length) lines.push(field('civics', ctx.empireCivics.join(', ')))
      if (ctx.dlcs?.length) lines.push(`- ${t('report.markdown.fields.dlcs', { count: ctx.dlcs.length })}`)
      if (ctx.ingestionLastError) lines.push(field('ingestionLastError', ctx.ingestionLastError))
      if (ctx.warDiagnostics) {
        const warDiagnosticsJson = JSON.stringify(ctx.warDiagnostics, null, 2)
        lines.push('')
        lines.push(`<details><summary>${t('report.markdown.warDiagnostics')}</summary>`)
        lines.push('')
        lines.push('```json')
        lines.push(warDiagnosticsJson.length > 24_000
          ? `${warDiagnosticsJson.slice(0, 24_000).trimEnd()}...`
          : warDiagnosticsJson)
        lines.push('```')
        lines.push('')
        lines.push('</details>')
      }
      lines.push('')
    }

    if (ctx.error) {
      lines.push(`## ${t('report.markdown.errorContext')}`)
      lines.push(field('source', ctx.error.source))
      lines.push(field('message', ctx.error.message))
      if (ctx.error.stack) {
        lines.push('')
        lines.push(`<details><summary>${t('report.markdown.stackTrace')}</summary>`)
        lines.push('')
        lines.push('```text')
        lines.push(ctx.error.stack)
        lines.push('```')
        lines.push('')
        lines.push('</details>')
      }
      lines.push('')
    }

    if (ctx.llm) {
      lines.push(`## ${t('report.markdown.llmContext')}`)
      lines.push(`<details><summary>${t('report.markdown.promptResponse')}</summary>`)
      lines.push('')
      if (ctx.llm.model) lines.push(field('model', ctx.llm.model))
      if (typeof ctx.llm.responseTimeMs === 'number') lines.push(field('responseTime', ctx.llm.responseTimeMs))
      if (ctx.llm.model || typeof ctx.llm.responseTimeMs === 'number') lines.push('')
      if (ctx.llm.lastPrompt) {
        lines.push(`### ${t('report.markdown.prompt')}`)
        lines.push('```text')
        lines.push(ctx.llm.lastPrompt)
        lines.push('```')
        lines.push('')
      }
      if (ctx.llm.lastResponse) {
        lines.push(`### ${t('report.markdown.response')}`)
        lines.push('```text')
        lines.push(ctx.llm.lastResponse)
        lines.push('```')
        lines.push('')
      }
      if (ctx.llm.recentTurns?.length) {
        lines.push(`### ${t('report.markdown.recentTurns')}`)
        lines.push('```text')
        for (const turn of ctx.llm.recentTurns) {
          lines.push(`${t(turn.role === 'user' ? 'report.markdown.user' : 'report.markdown.advisor')}: ${turn.content}`)
        }
        lines.push('```')
        lines.push('')
      }
      lines.push('</details>')
      lines.push('')
    }

    if (backendLogTail) {
      lines.push(`## ${t('report.markdown.backendLogTail')}`)
      lines.push(`<details><summary>${t('report.markdown.last32KB')}</summary>`)
      lines.push('')
      lines.push('```text')
      lines.push(backendLogTail)
      lines.push('```')
      lines.push('')
      lines.push('</details>')
      lines.push('')
    }

    if (includeScreenshot) {
      lines.push(`## ${t('report.markdown.screenshot')}`)
      lines.push(`- ${t('report.markdown.screenshotRequested')}`)
      lines.push(`- ${t('report.markdown.screenshotHelp')}`)
      lines.push('')
    }

    lines.push(`## ${t('report.markdown.stepsToReproduce')}`)
    lines.push(`1. ${t('report.markdown.fillIn')}`)
    lines.push('2. ')
    lines.push('3. ')
    lines.push('')

    return lines.join('\n')
  }

  async function buildReport(): Promise<string> {
    const fallbackInfo = window.electronAPI?.getPlatformInfo?.()
    const base = context || {
      appVersion: 'unknown',
      platform: fallbackInfo ? `${fallbackInfo.platform}-${fallbackInfo.arch}` : navigator.platform,
      electronVersion: navigator.userAgent.match(/Electron\/([\d.]+)/)?.[1] || 'unknown',
    }

    const enriched = await enrichContext(base)

    let backendLogTail: string | undefined
    if (includeBackendLogs) {
      const resp = await window.electronAPI?.getBackendLogTail?.({ maxBytes: 32 * 1024 })
      if (resp && typeof resp === 'object' && 'ok' in resp && resp.ok) {
        backendLogTail = resp.data
      }
    }

    return formatReportMarkdown(enriched, backendLogTail)
  }

  async function submitToWorker() {
    if (!category || !description.trim()) return
    if (!REPORT_ENDPOINT) {
      setStatus(t('report.submitUnavailable'))
      return
    }

    setBusy(true)
    try {
      const fallbackInfo = window.electronAPI?.getPlatformInfo?.()
      const base = context || {
        appVersion: await window.electronAPI?.getAppVersion?.() || 'unknown',
        platform: fallbackInfo ? `${fallbackInfo.platform}-${fallbackInfo.arch}` : navigator.platform,
        electronVersion: navigator.userAgent.match(/Electron\/([\d.]+)/)?.[1] || 'unknown',
      }
      const enriched = await enrichContext(base)

      const installId = await window.electronAPI?.getInstallId?.()

      let backendLogTail: string | undefined
      if (includeBackendLogs) {
        const resp = await window.electronAPI?.getBackendLogTail?.({ maxBytes: 32 * 1024 })
        if (resp && typeof resp === 'object' && 'ok' in resp && resp.ok) {
          backendLogTail = resp.data
        }
      }

      let screenshot: string | undefined
      if (includeScreenshot) {
        screenshot = await window.electronAPI?.captureScreenshot?.() || undefined
        // Avoid shipping multi-megabyte screenshots by accident.
        if (screenshot && screenshot.length > 2_000_000) {
          screenshot = undefined
        }
      }

      const payload = {
        schema_version: 2,
        submitted_at_ms: Date.now(),
        install_id: typeof installId === 'string' ? installId : undefined,
        category,
        description: description.trim(),
        context: {
          appVersion: enriched.appVersion,
          platform: enriched.platform,
          electronVersion: enriched.electronVersion,
          // Opt-in sections
          diagnostics: includeDiagnostics
            ? {
              stellarisVersion: enriched.stellarisVersion,
              dlcs: enriched.dlcs,
              empireName: enriched.empireName,
              empireType: enriched.empireType,
              empireOrigin: enriched.empireOrigin,
              empireEthics: enriched.empireEthics,
              empireCivics: enriched.empireCivics,
              gameYear: enriched.gameYear,
              saveFileSizeMb: enriched.saveFileSizeMb,
              galaxySize: enriched.galaxySize,
              ingestionStage: enriched.ingestionStage,
              ingestionStageDetail: enriched.ingestionStageDetail,
              ingestionLastError: enriched.ingestionLastError,
              precomputeReady: enriched.precomputeReady,
              t2Ready: enriched.t2Ready,
              warDiagnostics: enriched.warDiagnostics,
            }
            : undefined,
          error: includeErrorContext ? enriched.error : undefined,
          llm: includeLlmContext ? enriched.llm : undefined,
          backend_log_tail: includeBackendLogs ? backendLogTail : undefined,
          screenshot: includeScreenshot ? screenshot : undefined,
        },
      }

      const res = await fetch(REPORT_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        const issueUrl = typeof data.issueUrl === 'string' ? data.issueUrl : undefined
        setStatus(issueUrl ? t('report.submittedIssue', { issueUrl }) : t('report.submitted'))
      } else {
        const msg = typeof data.error === 'string' ? data.error : `Submit failed (${res.status})`
        setStatus(t('report.submitFailedDetail', { detail: msg }))
      }
    } catch (e) {
      setStatus(t('report.submitFailedDetail', { detail: e instanceof Error ? e.message : '' }))
    } finally {
      setBusy(false)
    }
  }

  async function copyReportToClipboard() {
    if (!category || !description.trim()) return
    setBusy(true)
    try {
      const report = await buildReport()
      const resp = await window.electronAPI?.copyToClipboard?.(report)
      setStatus(t(resp?.success ? 'report.copied' : 'report.copyFailed'))
    } catch (e) {
      setStatus(t('report.buildFailedDetail', { detail: e instanceof Error ? e.message : '' }))
    } finally {
      setBusy(false)
    }
  }

  async function openIssuePage() {
    if (!category || !description.trim()) return
    setBusy(true)
    try {
      const report = await buildReport()
      const resp = await window.electronAPI?.copyToClipboard?.(report)
      if (!resp?.success) {
        setStatus(t('report.copyFailed'))
        return
      }
      const title = encodeURIComponent(`[${category}] ${description.trim().slice(0, 60)}`)
      const body = encodeURIComponent(t('report.markdown.issueBody'))
      const url = `${ISSUE_URL}?title=${title}&body=${body}`
      await window.electronAPI?.openExternal?.(url)
      setStatus(t('report.openedGithub'))
    } catch (e) {
      setStatus(t('report.openFailedDetail', { detail: e instanceof Error ? e.message : '' }))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={isOpen} onClose={busy ? undefined : onClose} labelledBy="report-issue-title" className="w-full max-w-lg p-6 overflow-y-auto custom-scrollbar">
          <div className="absolute top-0 left-0 w-4 h-4 border-l-2 border-t-2 border-accent-cyan/60" />
          <div className="absolute top-0 right-0 w-4 h-4 border-r-2 border-t-2 border-accent-cyan/60" />
          <div className="absolute bottom-0 left-0 w-4 h-4 border-l-2 border-b-2 border-accent-cyan/60" />
          <div className="absolute bottom-0 right-0 w-4 h-4 border-r-2 border-b-2 border-accent-cyan/60" />

          <h2 id="report-issue-title" className="text-lg font-semibold text-text-primary uppercase tracking-wider mb-5 flex items-center gap-2">
            <span className="text-accent-cyan">◈</span>
            {t('report.title')}
          </h2>

          <div className="space-y-5">
            <HUDSelect
              label={t('report.category')}
              options={[
                { value: '', label: t('report.selectCategory') },
                ...CATEGORIES.map(cat => ({ value: cat, label: t(`report.categories.${cat}`) })),
              ]}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />

            <div className="flex flex-col gap-1.5">
              <span className="font-display text-[10px] tracking-widest text-text-secondary uppercase pl-1">
                {t('report.description')}
              </span>
              <HUDTextArea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('report.descriptionPlaceholder')}
                rows={4}
              />
            </div>

            {context && (
              <div className="p-3 bg-black/20 border border-white/5 rounded-sm">
                <div className="font-display text-[10px] tracking-widest text-text-secondary uppercase mb-2">
                  {t('report.autoCaptured')}
                </div>
                <div className="space-y-1 text-xs text-text-secondary font-mono">
                  <div>{t('report.app')} <span className="text-text-primary">{context.appVersion}</span></div>
                  <div>{t('report.platform')} <span className="text-text-primary">{context.platform}</span></div>
                  <div>Electron <span className="text-text-primary">{context.electronVersion}</span></div>
                </div>
              </div>
            )}

            <div className="space-y-3">
              <span className="font-display text-[10px] tracking-widest text-text-secondary uppercase pl-1">
                {t('report.optional')}
              </span>
              <HUDCheckbox
                label={t('report.includeDiagnostics')}
                checked={includeDiagnostics}
                onChange={(e) => setIncludeDiagnostics(e.target.checked)}
              />
              <HUDCheckbox
                label={t('report.includeLogs')}
                checked={includeBackendLogs}
                onChange={(e) => setIncludeBackendLogs(e.target.checked)}
              />
              <HUDCheckbox
                label={t('report.includeScreenshot')}
                checked={includeScreenshot}
                onChange={(e) => setIncludeScreenshot(e.target.checked)}
              />
              {prefill?.error && (
                <HUDCheckbox
                  label={t('report.includeError')}
                  checked={includeErrorContext}
                  onChange={(e) => setIncludeErrorContext(e.target.checked)}
                />
              )}
              {prefill?.llm && (
                <HUDCheckbox
                  label={t('report.includeLlm')}
                  checked={includeLlmContext}
                  onChange={(e) => setIncludeLlmContext(e.target.checked)}
                />
              )}
            </div>

            {status && (
              <div className="p-3 bg-black/20 border border-white/10 rounded-sm text-xs text-text-secondary font-mono">
                {status}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <HUDButton
                variant="primary"
                onClick={submitToWorker}
                disabled={!category || !description.trim() || busy || !REPORT_ENDPOINT}
                title={!REPORT_ENDPOINT ? t('report.submitUnavailableHint') : undefined}
                className="w-full"
              >
                {busy ? t('report.working') : t('report.submit')}
              </HUDButton>
              <HUDButton
                variant="primary"
                onClick={copyReportToClipboard}
                disabled={!category || !description.trim() || busy}
                className="w-full"
              >
                {busy ? t('report.working') : t('report.copy')}
              </HUDButton>
              <HUDButton
                variant="secondary"
                onClick={openIssuePage}
                disabled={!category || !description.trim() || busy}
                className="w-full"
              >
                {t('report.github')}
              </HUDButton>
            </div>

            <HUDButton
              variant="ghost"
              onClick={onClose}
              className="w-full"
            >
              {t('report.close')}
            </HUDButton>
          </div>
    </Modal>
  )
}
