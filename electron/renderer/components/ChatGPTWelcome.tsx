import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useChatGPT, manageChatGPTUsage } from '../hooks/useChatGPT'
import { HUDPanel } from './hud/HUDPanel'
import { HUDButton } from './hud/HUDButton'
import type { Settings } from '../hooks/useSettings'
import logo from '../assets/chatgpt-logo-white.svg'

export default function ChatGPTWelcome({ enabled }: { enabled: boolean }) {
  const { t } = useTranslation()
  const { status, accept } = useChatGPT()
  const [active, setActive] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(false)
  const dialog = useRef<HTMLDivElement>(null)
  const open = enabled && active && status?.ready && status.welcomePending
  useEffect(() => {
    let live = true
    if (enabled && status?.ready && status.welcomePending) {
      void window.electronAPI?.getSettings().then(raw => { if (live) setActive((raw as Settings).advisorProvider === 'chatgpt') }).catch(() => {})
    } else setActive(false)
    return () => { live = false }
  }, [enabled, status])
  const dismiss = async () => {
    if (saving) return
    setSaving(true); setError(false)
    try {
      const result = await window.electronAPI?.chatgpt.acknowledgeWelcome()
      if (!result?.ok) throw new Error('acknowledge')
      accept(result)
    } catch { setError(true) }
    finally { setSaving(false) }
  }
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.querySelector<HTMLButtonElement>('[data-dismiss]')?.focus()
    return () => previous?.focus()
  }, [open])
  if (!open) return null
  return createPortal(<div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onKeyDown={event => {
    if (event.key === 'Escape') void dismiss()
    if (event.key === 'Tab') {
      const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
      const next = buttons[(buttons.indexOf(document.activeElement as HTMLButtonElement) + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length]
      event.preventDefault(); next?.focus()
    }
  }}>
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="chatgpt-welcome-title" className="w-full max-w-[560px]" style={{ height: 'min(300px, calc(100dvh - 32px))' }}>
      <HUDPanel className="h-full bg-bg-secondary border border-accent-cyan/35 shadow-panel-cyan-soft" decoration="brackets" noPadding>
        <div className="flex h-full flex-col gap-6 p-6">
          <h2 id="chatgpt-welcome-title" className="flex shrink-0 items-center gap-3 font-display text-base leading-6 tracking-[0.08em] uppercase"><img src={logo} alt="" className="h-7 w-7" />{t('chatgpt.welcomeTitle')}</h2>
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto"><p className="text-base leading-6 text-text-secondary">{t('chatgpt.welcomeDescription')}</p>
            <button type="button" onClick={() => void manageChatGPTUsage()} className="self-start text-sm text-accent-cyan hover:underline">{t('chatgpt.manageUsage')} ↗</button>
            {error && <p role="alert" className="text-sm text-accent-red">{t('onboarding.slim.saveError')}</p>}
          </div>
          <div className="flex shrink-0 justify-end"><HUDButton data-dismiss disabled={saving} onClick={() => void dismiss()} className="min-h-[42px]">{t('chatgpt.gotIt')}</HUDButton></div>
        </div>
      </HUDPanel>
    </div>
  </div>, document.body)
}
