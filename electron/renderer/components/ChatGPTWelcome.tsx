import { useEffect, useState } from 'react'
import Modal from './Modal'
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
  return <Modal open={Boolean(open)} onClose={saving ? undefined : () => void dismiss()} labelledBy="chatgpt-welcome-title" className="w-full max-w-[560px] h-[min(320px,calc(100dvh-32px))]">
      <HUDPanel className="h-full bg-bg-secondary border border-accent-cyan/35 shadow-panel-cyan-soft" decoration="brackets" noPadding>
        <div className="flex h-full flex-col gap-6 p-6">
          <h2 id="chatgpt-welcome-title" className="flex shrink-0 items-center gap-3 font-display text-base leading-6 tracking-[0.08em] uppercase"><img src={logo} alt="" className="h-7 w-7" />{t('chatgpt.welcomeTitle')}</h2>
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto"><p className="text-base leading-6 text-text-secondary">{t('chatgpt.welcomeDescription')}</p>
            <button type="button" onClick={() => void manageChatGPTUsage()} className="self-start text-sm text-accent-cyan hover:underline">{t('chatgpt.manageUsage')} ↗</button>
            {error && <p role="alert" className="text-sm text-accent-red">{t('onboarding.slim.saveError')}</p>}
          </div>
          <div className="flex shrink-0 justify-end"><HUDButton data-dismiss data-modal-autofocus disabled={saving} onClick={() => void dismiss()} className="min-h-[42px]">{t('chatgpt.gotIt')}</HUDButton></div>
        </div>
      </HUDPanel>
  </Modal>
}
