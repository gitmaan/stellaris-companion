import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HUDButton } from './hud/HUDButton'
import { HUDCheckbox } from './hud/HUDForm'

interface Props {
  selected: ReportSavePreview | null
  onSelect: (save: ReportSavePreview | null) => void
  consent: boolean
  onConsent: (consent: boolean) => void
  busy: boolean
  submitted: boolean
  refresh: number
  onBusy: (busy: boolean) => void
  onStatus: (status: string) => void
}

export default function ReportSaveAttachments({ selected, onSelect, consent, onConsent, busy, submitted, refresh, onBusy, onStatus }: Props) {
  const { t } = useTranslation()
  const [receipts, setReceipts] = useState<ReportSaveReceipt[]>([])
  const [revision, setRevision] = useState(0)
  const [progress, setProgress] = useState<number | null>(null)
  useEffect(() => {
    let live = true
    window.electronAPI?.reportSaves?.list().then(result => {
      if (live && result.ok) setReceipts(result.data)
    }).catch(() => {})
    return () => { live = false }
  }, [refresh, revision])
  useEffect(() => window.electronAPI?.reportSaves?.onProgress(event => setProgress(event.percent)), [])

  async function act(action: () => Promise<void>) {
    onBusy(true)
    setProgress(null)
    try { await action() }
    catch (error) { onStatus(error instanceof Error ? error.message : t('report.saves.failed')) }
    finally { onBusy(false); setRevision(value => value + 1) }
  }
  return <section className="space-y-3 border border-white/10 rounded-sm p-3">
    <p className="text-sm text-text-primary">{t('report.saves.title')}</p>
    {!submitted && <>
      <HUDButton variant="secondary" disabled={busy || !window.electronAPI?.reportSaves} onClick={() => void act(async () => {
        onConsent(false)
        onSelect(null)
        if (!window.electronAPI?.reportSaves) throw new Error(t('report.saves.failed'))
        const result = await window.electronAPI.reportSaves.select()
        if (!result.ok) throw new Error(result.error)
        onSelect(result.data)
      })}>{t(selected ? 'report.saves.refresh' : 'report.saves.select')}</HUDButton>
      {selected && <>
        <p className="text-xs text-text-secondary break-words">{t('report.saves.preview', { empire: selected.empireName || t('report.saves.unknownEmpire'), date: selected.gameDate, version: selected.gameVersion, filename: selected.filename, size: (selected.sizeBytes / 1048576).toFixed(2) })}</p>
        <HUDCheckbox disabled={busy} label={t('report.saves.consent')} checked={consent} onChange={event => onConsent(event.target.checked)} />
        <p className="text-xs text-text-secondary">{t('report.saves.privacy')}</p>
        <a className="text-accent-cyan underline text-xs" href="https://galacticfilingcabinet.com/privacy#report-saves" onClick={event => { event.preventDefault(); void window.electronAPI?.openExternal('https://galacticfilingcabinet.com/privacy#report-saves') }}>{t('report.saves.policy')}</a>
      </>}
    </>}
    {busy && progress !== null && <div role="status" className="text-xs text-text-secondary">
      <p>{t('report.saves.progress', { percent: progress })}</p>
      <progress className="w-full" max={100} value={progress} aria-label={t('report.saves.upload')} />
    </div>}
    {receipts.length > 0 && <div className="space-y-3">
      <p className="text-xs text-text-secondary">{t('report.saves.history')}</p>
      {receipts.map(receipt => <div key={receipt.id} className="space-y-2 border-t border-white/10 pt-2">
        <p className="text-xs text-text-primary break-all">{receipt.filename} · {t(`report.saves.${receipt.status}`)}</p>
        <p className="text-xs text-text-secondary break-all">{t('report.saves.receipt', { id: receipt.id, date: new Date(receipt.expiresAt).toLocaleDateString() })}</p>
        {receipt.issueUrl && <a className="text-xs underline text-accent-cyan" href={receipt.issueUrl} onClick={event => { event.preventDefault(); void window.electronAPI?.openExternal(receipt.issueUrl!) }}>{t('report.saves.issue')}</a>}
        <div className="flex gap-2">
          {receipt.status === 'pending' && <HUDButton variant="secondary" disabled={busy} onClick={() => void act(async () => {
            if (!window.electronAPI?.reportSaves) throw new Error(t('report.saves.failed'))
        const result = await window.electronAPI.reportSaves.retry(receipt.id)
            if (!result.ok) throw new Error(result.error)
            onStatus(t('report.saves.uploaded'))
          })}>{t('report.saves.retry')}</HUDButton>}
          <HUDButton variant="ghost" disabled={busy} onClick={() => void act(async () => {
            if (!window.electronAPI?.reportSaves) throw new Error(t('report.saves.failed'))
        const result = await window.electronAPI.reportSaves.remove(receipt.id)
            if (!result.ok) throw new Error(result.error)
            onStatus(t('report.saves.deleted'))
          })}>{t('report.saves.delete')}</HUDButton>
        </div>
      </div>)}
    </div>}
  </section>
}
