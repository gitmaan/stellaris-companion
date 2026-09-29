import { useCallback, useState } from 'react'
import { useToast } from '../components/Toast'
import { useTranslation } from 'react-i18next'

interface ErrorContext {
  message: string
  stack?: string
  source: 'extraction' | 'llm' | 'ui' | 'ipc' | 'unknown'
}

interface LlmTurn {
  role: 'user' | 'assistant'
  content: string
}

interface LlmContext {
  lastPrompt?: string
  lastResponse?: string
  recentTurns?: LlmTurn[]
  responseTimeMs?: number
  model?: string
}

interface ModalPrefill {
  category?: string
  error?: ErrorContext
  llm?: LlmContext
}

/**
 * useErrorReporter - Hook for prompting error reports via toast + modal
 *
 * Provides methods to:
 * - promptErrorReport: Show toast for errors with "Report" action
 * - promptLLMReport: Show toast for suspicious LLM responses
 * - openReportModal: Open report modal directly (for Settings page)
 */
export function useErrorReporter() {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const [modalOpen, setModalOpen] = useState(false)
  const [modalPrefill, setModalPrefill] = useState<ModalPrefill | null>(null)

  const openLLMReportModal = useCallback((llm: LlmContext) => {
    setModalPrefill({
      category: 'Strange LLM Response',
      llm,
    })
    setModalOpen(true)
  }, [])

  /**
   * Prompt user to report an error via toast notification
   */
  const promptErrorReport = useCallback((error: Error, source: ErrorContext['source']) => {
    const errorContext: ErrorContext = {
      message: error.message,
      stack: error.stack,
      source,
    }

    showToast({
      type: 'error',
      message: t('recovery.somethingWentWrong'),
      duration: 10000,
      action: {
        label: t('recovery.report'),
        onClick: () => {
          setModalPrefill({ category: 'Bug', error: errorContext })
          setModalOpen(true)
        },
      },
    })
  }, [showToast, t])

  /**
   * Prompt user to report a suspicious LLM response
   */
  const promptLLMReport = useCallback((llm: LlmContext) => {
    showToast({
      type: 'warning',
      message: t('recovery.responseOff'),
      duration: 15000,
      action: {
        label: t('recovery.report'),
        onClick: () => openLLMReportModal(llm),
      },
    })
  }, [showToast, openLLMReportModal, t])

  /**
   * Open the report modal directly (without toast)
   * Used for Settings page "Report Issue" button
   */
  const openReportModal = useCallback(() => {
    setModalPrefill(null)
    setModalOpen(true)
  }, [])

  /**
   * Close the modal
   */
  const closeModal = useCallback(() => {
    setModalOpen(false)
    setModalPrefill(null)
  }, [])

  return {
    promptErrorReport,
    promptLLMReport,
    openLLMReportModal,
    openReportModal,
    modalOpen,
    modalPrefill,
    closeModal,
  }
}

export default useErrorReporter
