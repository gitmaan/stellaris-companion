import { useState, useEffect, createContext, useContext, useCallback, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { motionTiming } from '../lib/motion'

interface Toast {
  id: string
  type: 'error' | 'warning' | 'success' | 'info'
  message: string
  action?: {
    label: string
    onClick: () => void
  }
  duration?: number
}

interface ToastContextValue {
  showToast: (toast: Omit<Toast, 'id'>) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within ToastProvider')
  return context
}

const typeStyles = {
  error: 'border-accent-red/40 text-accent-red',
  warning: 'border-accent-yellow/40 text-accent-yellow',
  success: 'border-accent-green/40 text-accent-green',
  info: 'border-accent-cyan/40 text-accent-cyan',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const showToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { ...toast, id }])
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {createPortal(
        <div data-notifications className="fixed top-32 right-4 z-[10001] w-96 max-w-[calc(100vw-2rem)] max-h-[calc(100dvh-17rem)] overflow-y-auto flex flex-col gap-2 pointer-events-none">
          <AnimatePresence>
            {toasts.map(toast => <ToastNotice key={toast.id} toast={toast} dismiss={dismiss} />)}
          </AnimatePresence>
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  )
}

function ToastNotice({ toast, dismiss }: { toast: Toast; dismiss: (id: string) => void }) {
  const { t } = useTranslation()
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  useEffect(() => {
    if (hovered || focused || toast.duration === 0) return
    const timer = setTimeout(() => dismiss(toast.id), toast.duration ?? 8000)
    return () => clearTimeout(timer)
  }, [toast, dismiss, hovered, focused])
  return <motion.div
                key={toast.id}
                onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
                onFocusCapture={() => setFocused(true)} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false) }}
                role={toast.type === 'error' ? 'alert' : 'status'}
                aria-atomic="true"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: motionTiming.content }}
                className={`relative shrink-0 w-full p-4 rounded-lg border bg-bg-secondary pointer-events-auto ${typeStyles[toast.type]}`}
                style={{ boxShadow: '0 0 20px rgba(0, 0, 0, 0.4)' }}
              >
                {/* Corner accents */}
                <div className="absolute top-0 left-0 w-2 h-2 border-l border-t border-current opacity-60" />
                <div className="absolute top-0 right-0 w-2 h-2 border-r border-t border-current opacity-60" />
                <div className="absolute bottom-0 left-0 w-2 h-2 border-l border-b border-current opacity-60" />
                <div className="absolute bottom-0 right-0 w-2 h-2 border-r border-b border-current opacity-60" />

                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-text-primary flex-1">{toast.message}</p>
                  <button
                    onClick={() => dismiss(toast.id)}
                    aria-label={t('common.close')}
                    className="text-text-secondary hover:text-text-primary transition-colors text-lg leading-none"
                  >
                    ×
                  </button>
                </div>

                {toast.action && (
                  <button
                    onClick={() => {
                      toast.action!.onClick()
                      dismiss(toast.id)
                    }}
                    className="mt-3 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider rounded border border-current/50 hover:bg-current/20 transition-colors"
                  >
                    {toast.action.label}
                  </button>
                )}
              </motion.div>
}

export default ToastProvider
