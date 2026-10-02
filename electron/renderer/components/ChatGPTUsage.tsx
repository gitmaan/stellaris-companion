import { useTranslation } from 'react-i18next'
import { manageChatGPTUsage } from '../hooks/useChatGPT'
import ChatGPTModelPicker from './ChatGPTModelPicker'

export default function ChatGPTUsage({ disabled = false }: { disabled?: boolean }) {
  const { t } = useTranslation()
  return <div className="flex flex-wrap justify-between items-center gap-2 px-1 py-2 text-[11px] text-text-secondary">
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
      <span>{t('chatgpt.usingPlan')}</span>
      <ChatGPTModelPicker compact disabled={disabled} />
    </div>
    <button type="button" onClick={() => void manageChatGPTUsage()} className="text-accent-cyan hover:underline">{t('chatgpt.manageUsage')}</button>
  </div>
}
