import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { HUDButton } from './hud/HUDButton'
import { HUDSelect, HUDCheckbox } from './hud/HUDForm'
import { HUDTextArea } from './hud/HUDInput'

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
    setIncludeErrorContext(!!prefill?.error)
    setIncludeLlmContext(!!prefill?.llm)
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

    lines.push(`# ${category || 'Report'}`)
    lines.push('')
    lines.push('## What happened')
    lines.push(description.trim() || '(fill in)')
    lines.push('')
    lines.push('## Environment')
    lines.push(`- App version: ${ctx.appVersion}`)
    lines.push(`- Platform: ${ctx.platform}`)
    lines.push(`- Electron: ${ctx.electronVersion}`)
    lines.push('')

    if (includeDiagnostics) {
      lines.push('## Game context (opt-in)')
      if (ctx.stellarisVersion) lines.push(`- Stellaris version: ${ctx.stellarisVersion}`)
      if (typeof ctx.saveFileSizeMb === 'number') lines.push(`- Save size: ${ctx.saveFileSizeMb} MB`)
      if (ctx.galaxySize) lines.push(`- Galaxy size: ${ctx.galaxySize}`)
      if (ctx.gameYear) lines.push(`- Game date/year: ${ctx.gameYear}`)
      if (ctx.ingestionStage) lines.push(`- Ingestion stage: ${ctx.ingestionStage}`)
      if (ctx.ingestionStageDetail) lines.push(`- Ingestion detail: ${ctx.ingestionStageDetail}`)
      if (typeof ctx.precomputeReady === 'boolean') lines.push(`- Precompute ready: ${ctx.precomputeReady}`)
      if (typeof ctx.t2Ready === 'boolean') lines.push(`- Tier 2 ready: ${ctx.t2Ready}`)
      if (ctx.empireName) lines.push(`- Empire: ${ctx.empireName}`)
      if (ctx.empireType) lines.push(`- Empire type: ${ctx.empireType}`)
      if (ctx.empireOrigin) lines.push(`- Origin: ${ctx.empireOrigin}`)
      if (ctx.empireEthics?.length) lines.push(`- Ethics: ${ctx.empireEthics.join(', ')}`)
      if (ctx.empireCivics?.length) lines.push(`- Civics: ${ctx.empireCivics.join(', ')}`)
      if (ctx.dlcs?.length) lines.push(`- DLCs: ${ctx.dlcs.length} enabled`)
      if (ctx.ingestionLastError) lines.push(`- Ingestion last error: ${ctx.ingestionLastError}`)
      lines.push('')
    }

    if (ctx.error) {
      lines.push('## Error context (opt-in)')
      lines.push(`- Source: ${ctx.error.source}`)
      lines.push(`- Message: ${ctx.error.message}`)
      if (ctx.error.stack) {
        lines.push('')
        lines.push('<details><summary>Stack trace</summary>')
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
      lines.push('## LLM context (opt-in)')
      lines.push('<details><summary>Prompt/response</summary>')
      lines.push('')
      if (ctx.llm.model) lines.push(`- Model: ${ctx.llm.model}`)
      if (typeof ctx.llm.responseTimeMs === 'number') lines.push(`- Response time: ${ctx.llm.responseTimeMs}ms`)
      if (ctx.llm.model || typeof ctx.llm.responseTimeMs === 'number') lines.push('')
      if (ctx.llm.lastPrompt) {
        lines.push('### Prompt')
        lines.push('```text')
        lines.push(ctx.llm.lastPrompt)
        lines.push('```')
        lines.push('')
      }
      if (ctx.llm.lastResponse) {
        lines.push('### Response')
        lines.push('```text')
        lines.push(ctx.llm.lastResponse)
        lines.push('```')
        lines.push('')
      }
      if (ctx.llm.recentTurns?.length) {
        lines.push('### Recent turns')
        lines.push('```text')
        for (const turn of ctx.llm.recentTurns) {
          lines.push(`${turn.role === 'user' ? 'User' : 'Advisor'}: ${turn.content}`)
        }
        lines.push('```')
        lines.push('')
      }
      lines.push('</details>')
      lines.push('')
    }

    if (backendLogTail) {
      lines.push('## Backend log tail (opt-in)')
      lines.push('<details><summary>Last ~32KB</summary>')
      lines.push('')
      lines.push('```text')
      lines.push(backendLogTail)
      lines.push('```')
      lines.push('')
      lines.push('</details>')
      lines.push('')
    }

    if (includeScreenshot) {
      lines.push('## Screenshot (opt-in)')
      lines.push('- Screenshot requested.')
      lines.push('- Use "Submit" for automatic screenshot upload; clipboard report omits raw image bytes.')
      lines.push('')
    }

    lines.push('## Steps to reproduce')
    lines.push('1. (fill in)')
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
      setStatus('Submit is not configured for this build. Use “Copy Report” instead.')
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
        schema_version: 1,
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
        setStatus(issueUrl ? `Submitted. Issue: ${issueUrl}` : 'Submitted. Thank you!')
      } else {
        const msg = typeof data.error === 'string' ? data.error : `Submit failed (${res.status})`
        setStatus(msg)
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Submit failed')
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
      setStatus(resp?.success ? 'Copied report to clipboard. Paste it into your issue/feedback.' : 'Failed to copy to clipboard.')
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Failed to build report')
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
        setStatus('Failed to copy report to clipboard.')
        return
      }
      const title = encodeURIComponent(`[${category}] ${description.trim().slice(0, 60)}`)
      const body = encodeURIComponent('Paste the report from your clipboard here.\n\n(Generated by Stellaris Companion)')
      const url = `${ISSUE_URL}?title=${title}&body=${body}`
      await window.electronAPI?.openExternal?.(url)
      setStatus('Opened GitHub. Paste the report from your clipboard into the editor.')
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Failed to open issue page')
    } finally {
      setBusy(false)
    }
  }

  if (!isOpen) return null

  return createPortal(
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.2 }}
          className="relative w-full max-w-lg mx-4 p-6 bg-bg-elevated border border-border rounded-lg"
          style={{ boxShadow: '0 0 40px rgba(0, 212, 255, 0.1), 0 8px 32px rgba(0, 0, 0, 0.5)' }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="absolute top-0 left-0 w-4 h-4 border-l-2 border-t-2 border-accent-cyan/60" />
          <div className="absolute top-0 right-0 w-4 h-4 border-r-2 border-t-2 border-accent-cyan/60" />
          <div className="absolute bottom-0 left-0 w-4 h-4 border-l-2 border-b-2 border-accent-cyan/60" />
          <div className="absolute bottom-0 right-0 w-4 h-4 border-r-2 border-b-2 border-accent-cyan/60" />

          <h2 className="text-lg font-semibold text-text-primary uppercase tracking-wider mb-5 flex items-center gap-2">
            <span className="text-accent-cyan">◈</span>
            Report Issue / Feedback
          </h2>

          <div className="space-y-5">
            <HUDSelect
              label="Category"
              options={[
                { value: '', label: 'Select category...' },
                ...CATEGORIES.map(cat => ({ value: cat, label: cat })),
              ]}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />

            <div className="flex flex-col gap-1.5">
              <span className="font-display text-[10px] tracking-widest text-text-secondary uppercase pl-1">
                Description
              </span>
              <HUDTextArea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What happened? What did you expect?"
                rows={4}
              />
            </div>

            {context && (
              <div className="p-3 bg-black/20 border border-white/5 rounded-sm">
                <div className="font-display text-[10px] tracking-widest text-text-secondary uppercase mb-2">
                  Auto-captured
                </div>
                <div className="space-y-1 text-xs text-text-secondary font-mono">
                  <div>App <span className="text-text-primary">{context.appVersion}</span></div>
                  <div>Platform <span className="text-text-primary">{context.platform}</span></div>
                  <div>Electron <span className="text-text-primary">{context.electronVersion}</span></div>
                </div>
              </div>
            )}

            <div className="space-y-3">
              <span className="font-display text-[10px] tracking-widest text-text-secondary uppercase pl-1">
                Optional (opt-in)
              </span>
              <HUDCheckbox
                label="Include game diagnostics (DLCs, empire, save metadata)"
                checked={includeDiagnostics}
                onChange={(e) => setIncludeDiagnostics(e.target.checked)}
              />
              <HUDCheckbox
                label="Include recent backend logs"
                checked={includeBackendLogs}
                onChange={(e) => setIncludeBackendLogs(e.target.checked)}
              />
              <HUDCheckbox
                label="Include screenshot"
                checked={includeScreenshot}
                onChange={(e) => setIncludeScreenshot(e.target.checked)}
              />
              {prefill?.error && (
                <HUDCheckbox
                  label="Include error details (message/stack)"
                  checked={includeErrorContext}
                  onChange={(e) => setIncludeErrorContext(e.target.checked)}
                />
              )}
              {prefill?.llm && (
                <HUDCheckbox
                  label="Include last prompt/response"
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
                title={!REPORT_ENDPOINT ? 'Submit is not configured for this build' : undefined}
                className="w-full"
              >
                {busy ? 'Working…' : 'Submit'}
              </HUDButton>
              <HUDButton
                variant="primary"
                onClick={copyReportToClipboard}
                disabled={!category || !description.trim() || busy}
                className="w-full"
              >
                {busy ? 'Working…' : 'Copy Report'}
              </HUDButton>
              <HUDButton
                variant="secondary"
                onClick={openIssuePage}
                disabled={!category || !description.trim() || busy}
                className="w-full"
              >
                GitHub Issue
              </HUDButton>
            </div>

            <HUDButton
              variant="ghost"
              onClick={onClose}
              className="w-full"
            >
              Close
            </HUDButton>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body,
  )
}
