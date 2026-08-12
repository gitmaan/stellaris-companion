import { useTranslation } from 'react-i18next'
import type { AdvisorProvider } from '../../hooks/useSettings'

interface ProviderSetupGuideProps {
  provider: AdvisorProvider
}

function guideGroup(provider: AdvisorProvider): 'gemini' | 'local' | 'hosted' | 'custom' {
  if (provider === 'gemini') return 'gemini'
  if (provider === 'ollama' || provider === 'lm_studio') return 'local'
  if (provider === 'custom') return 'custom'
  return 'hosted'
}

export function ProviderSetupGuide({ provider }: ProviderSetupGuideProps) {
  const { t } = useTranslation()
  const group = guideGroup(provider)

  return (
    <ol className="grid grid-cols-1 gap-2 sm:grid-cols-3" aria-label={t('settings.advisor.guide.label')}>
      {[1, 2, 3].map(step => (
        <li
          key={step}
          className="flex min-w-0 items-start gap-2 rounded-sm border border-white/10 bg-black/20 px-3 py-2"
        >
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-accent-cyan/40 font-mono text-[10px] text-accent-cyan">
            {step}
          </span>
          <span className="pt-0.5 text-xs leading-snug text-text-secondary">
            {t(`settings.advisor.guide.${group}.${step}`)}
          </span>
        </li>
      ))}
    </ol>
  )
}
