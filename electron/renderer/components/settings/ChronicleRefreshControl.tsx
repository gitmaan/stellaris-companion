import { useTranslation } from 'react-i18next'
import type { ChronicleRefreshMode } from '../../hooks/useSettings'
import { HUDLabel, HUDMicro } from '../hud/HUDText'

interface ChronicleRefreshControlProps {
  mode: ChronicleRefreshMode
  saving: boolean
  onChange: (mode: ChronicleRefreshMode) => void
}

export function ChronicleRefreshControl({
  mode,
  saving,
  onChange,
}: ChronicleRefreshControlProps) {
  const { t } = useTranslation()
  const options: ChronicleRefreshMode[] = ['balanced', 'enhanced']

  return (
    <div className="space-y-3 border-t border-white/10 pt-4">
      <div className="flex items-center justify-between gap-3">
        <HUDLabel>{t('settings.chronicleRefresh.label')}</HUDLabel>
        {saving && <HUDMicro className="text-right">{t('common.applying')}</HUDMicro>}
      </div>
      <div className="grid grid-cols-2 gap-2 rounded-sm border border-white/10 bg-black/20 p-1">
        {options.map(option => {
          const selected = mode === option
          return (
            <button
              key={option}
              type="button"
              disabled={saving}
              aria-pressed={selected}
              aria-label={t('settings.chronicleRefresh.aria', {
                mode: t(`settings.chronicleRefresh.${option}`),
              })}
              onClick={() => onChange(option)}
              className={`rounded-sm px-3 py-2 text-left transition-all duration-200 ${
                selected
                  ? 'border border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan'
                  : 'border border-transparent text-text-secondary hover:border-white/15 hover:bg-white/5'
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              <div className="font-display text-[11px] uppercase tracking-[0.18em]">
                {t(`settings.chronicleRefresh.${option}`)}
              </div>
              <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-white/35">
                {t(`settings.chronicleRefresh.${option}Tag`)}
              </div>
            </button>
          )
        })}
      </div>
      <HUDMicro className="block normal-case tracking-[0.02em] text-white/45">
        {t(`settings.chronicleRefresh.${mode}Help`)}
      </HUDMicro>
    </div>
  )
}
