import { useTranslation } from 'react-i18next'

/** Keep feedback beside its control and reserve space for both saving and idle hints. */
export function PreferenceFeedback({ saving, saved, hint }: { saving: boolean; saved?: boolean; hint?: string }) {
  const { t } = useTranslation()
  return <div className="grid font-mono text-[11px] leading-4 text-right text-text-secondary" data-preference-feedback>
    <span aria-hidden="true" className="invisible col-start-1 row-start-1">{hint}</span>
    <span aria-hidden="true" className="invisible col-start-1 row-start-1">{t('common.applying')}</span>
    <span role="status" aria-atomic="true" className={`col-start-1 row-start-1 ${saved && !saving ? 'text-accent-green' : ''}`}>
      {saving ? t('common.applying') : saved ? t('common.saved') : hint}
    </span>
  </div>
}
