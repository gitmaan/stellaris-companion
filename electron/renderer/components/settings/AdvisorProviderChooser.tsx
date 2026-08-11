import { useTranslation } from 'react-i18next'
import type { AdvisorProvider } from '../../hooks/useSettings'
import { HUDSelect } from '../hud/HUDForm'
import { HUDLabel, HUDMicro } from '../hud/HUDText'

type ProviderGroup = 'gemini' | 'local' | 'other'

interface AdvisorProviderChooserProps {
  provider: AdvisorProvider
  onChange: (provider: AdvisorProvider) => void
}

const LOCAL_PROVIDERS: AdvisorProvider[] = ['ollama', 'lm_studio']
const OTHER_PROVIDERS: AdvisorProvider[] = ['openrouter', 'custom']

function providerGroup(provider: AdvisorProvider): ProviderGroup {
  if (provider === 'gemini') return 'gemini'
  if (LOCAL_PROVIDERS.includes(provider)) return 'local'
  return OTHER_PROVIDERS.includes(provider) ? 'other' : 'gemini'
}

export function AdvisorProviderChooser({ provider, onChange }: AdvisorProviderChooserProps) {
  const { t } = useTranslation()
  const selectedGroup = providerGroup(provider)
  const groups: ProviderGroup[] = ['gemini', 'local', 'other']
  const groupIcons: Record<ProviderGroup, string> = {
    gemini: '✦',
    local: '▣',
    other: '◎',
  }

  const chooseGroup = (group: ProviderGroup) => {
    if (group === selectedGroup) return
    if (group === 'gemini') onChange('gemini')
    if (group === 'local') onChange('ollama')
    if (group === 'other') onChange('openrouter')
  }

  const providerOptions = selectedGroup === 'local'
    ? [
      { value: 'ollama', label: 'Ollama' },
      { value: 'lm_studio', label: 'LM Studio' },
    ]
    : [
      { value: 'openrouter', label: 'OpenRouter' },
      { value: 'custom', label: t('settings.advisor.providers.custom') },
    ]

  return (
    <div className="space-y-3">
      <HUDLabel>{t('settings.advisor.providerChoiceLabel')}</HUDLabel>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {groups.map(group => {
          const selected = selectedGroup === group
          return (
            <button
              key={group}
              type="button"
              aria-pressed={selected}
              onClick={() => chooseGroup(group)}
              className={`relative rounded-sm border px-3 py-2 text-left transition-all duration-200 ${
                selected
                  ? 'border-accent-cyan bg-accent-cyan/15 text-accent-cyan shadow-glow-sm'
                  : 'border-white/10 bg-black/20 text-text-secondary hover:border-white/20 hover:bg-white/5 hover:text-text-primary'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 font-display text-[11px] uppercase tracking-[0.16em]">
                  <span aria-hidden="true" className={selected ? 'text-accent-cyan' : 'text-white/35'}>
                    {groupIcons[group]}
                  </span>
                  {t(`settings.advisor.providerGroups.${group}`)}
                </span>
                {selected && (
                  <span
                    aria-hidden="true"
                    title={t('settings.advisor.selected')}
                    className="font-mono text-xs text-accent-green"
                  >
                    ✓
                  </span>
                )}
              </div>
              <HUDMicro className="mt-1 block text-[9px] text-white/40">
                {t(`settings.advisor.providerGroups.${group}Tag`)}
              </HUDMicro>
            </button>
          )
        })}
      </div>

      {selectedGroup !== 'gemini' && (
        <HUDSelect
          label={t(`settings.advisor.${selectedGroup}ProviderLabel`)}
          value={provider}
          onChange={event => onChange(event.target.value as AdvisorProvider)}
          options={providerOptions}
        />
      )}
    </div>
  )
}
