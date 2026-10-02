import type { ReactNode } from 'react'
import { HUDPanel } from './hud/HUDPanel'
import { useTranslation } from 'react-i18next'

export function OnboardingFrame({ step, title, icon, languageMenu, children, actions }: {
  step: number; title: string; icon?: ReactNode; languageMenu: ReactNode; children: ReactNode; actions: ReactNode
}) {
  const { t } = useTranslation()
  return <div data-onboarding-frame-step={step} className="h-full">
    <HUDPanel className="h-full bg-bg-secondary border border-accent-cyan/35 shadow-panel-cyan-soft" decoration="brackets" noPadding>
      <div className="flex h-full flex-col gap-6 p-6">
        <header className="flex shrink-0 flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0 flex-1 space-y-2">
            <p className="font-mono text-xs leading-4 tracking-[0.12em] uppercase text-accent-cyan">{t('onboarding.step', { current: step, total: 3 })}</p>
            <h1 id="onboarding-step-title" className="flex items-center gap-3 font-display text-xl leading-7 tracking-[0.12em] uppercase text-text-primary">{icon}{title}</h1>
          </div>
          {languageMenu}
        </header>
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto custom-scrollbar" data-onboarding-content>{children}</div>
        <div data-onboarding-actions-row="true" className="flex shrink-0 flex-wrap items-center justify-between gap-2 [&_button]:min-h-[42px] [&_button]:max-w-full">{actions}</div>
      </div>
    </HUDPanel>
  </div>
}

export function OnboardingIcon({ kind, className = 'h-6 w-6' }: { kind: string; className?: string }) {
  if (kind === 'folder') return <svg aria-hidden="true" viewBox="0 0 36 36" className={`shrink-0 text-accent-cyan ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
    <path d="M4 10h11l4 4h13v16H4V10Z" /><path d="M4 10V6h10l4 4h11v4" />
  </svg>
  return <svg aria-hidden="true" viewBox="0 0 24 24" className={`shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {kind === 'gemini' ? <path d="M12 2C12 8.2 8.2 12 2 12C8.2 12 12 15.8 12 22C12 15.8 15.8 12 22 12C15.8 12 12 8.2 12 2Z" />
      : kind === 'openrouter' ? <path d="M4 18V14C4 12.3 5.3 11 7 11H19M15 7L19 11L15 15M4 18V7C4 5.3 5.3 4 7 4H13M10 1L13 4L10 7" />
        : kind === 'error' ? <><path d="M8 8V5m8 3V5M7 8h10v4a5 5 0 0 1-10 0V8Zm5 9v5" /><path d="m10 10 4 4m0-4-4 4" /></>
          : <><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M9 2V6M15 2V6M9 18V22M15 18V22M2 9H6M2 15H6M18 9H22M18 15H22" /></>}
  </svg>
}

export function OnboardingSpinner() {
  return <span aria-hidden="true" className="inline-block h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-accent-cyan/15 border-t-accent-cyan" />
}
