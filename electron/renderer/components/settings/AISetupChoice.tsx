import { useTranslation } from 'react-i18next'

export type AISetupRoute = 'companion' | 'relay'

export function AISetupChoice({ value, onChange }: {
  value: AISetupRoute | null
  onChange: (value: AISetupRoute) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2" role="group" aria-label={t('settings.aiSetup.chooseRoute')}>
      {(['companion', 'relay'] as const).map(route => (
        <button
          key={route}
          type="button"
          aria-pressed={value === route}
          onClick={() => onChange(route)}
          className={`rounded border p-4 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-cyan ${value === route ? 'border-accent-cyan bg-accent-cyan/10' : 'border-white/20 bg-white/5 hover:border-accent-cyan/60'}`}
        >
          <span className="block font-display text-sm text-text-primary">{t(`settings.aiSetup.routes.${route}.title`)}</span>
          <span className="mt-2 block text-xs leading-relaxed text-text-secondary">{t(`settings.aiSetup.routes.${route}.description`)}</span>
        </button>
      ))}
    </div>
  )
}
