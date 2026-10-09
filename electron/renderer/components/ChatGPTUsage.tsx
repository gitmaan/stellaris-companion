import { useTranslation } from 'react-i18next'
import { manageChatGPTUsage } from '../hooks/useChatGPT'
import ChatGPTModelPicker from './ChatGPTModelPicker'

export default function ChatGPTUsage({ disabled = false }: { disabled?: boolean }) {
  const { t } = useTranslation()
  return <div className="flex h-12 justify-between items-center gap-2 px-1 text-[11px] text-text-secondary">
    <div className="flex flex-1 min-w-0 items-center gap-2">
      <span className="max-w-[45%] truncate" title={t('chatgpt.usingPlan')}>{t('chatgpt.usingPlan')}</span>
      <ChatGPTModelPicker compact disabled={disabled} />
    </div>
    <button type="button" onClick={() => void manageChatGPTUsage()} title={t('chatgpt.manageUsage')} className="max-w-[35%] shrink-0 truncate text-accent-cyan hover:underline">{t('chatgpt.manageUsage')}</button>
  </div>
}
