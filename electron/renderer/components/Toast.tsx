import { useState, createContext, useContext, useCallback, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'

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
  error: 'bg-accent-red/10 border-accent-red/40 text-accent-red',
  warning: 'bg-accent-yellow/10 border-accent-yellow/40 text-accent-yellow',
  success: 'bg-accent-green/10 border-accent-green/40 text-accent-green',
  info: 'bg-accent-cyan/10 border-accent-cyan/40 text-accent-cyan',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const showToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { ...toast, id }])

    // Auto-dismiss (duration: 0 means persistent)
    if (toast.duration !== 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id))
      }, toast.duration || 8000)
    }
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {createPortal(
        <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
          <AnimatePresence>
            {toasts.map(toast => (
              <motion.div
                key={toast.id}
                initial={{ opacity: 0, x: 50, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 50, scale: 0.95 }}
                transition={{ duration: 0.2 }}
                className={`relative min-w-[300px] max-w-[400px] p-4 rounded-lg border backdrop-blur-sm pointer-events-auto ${typeStyles[toast.type]}`}
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
            ))}
          </AnimatePresence>
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  )
}

export default ToastProvider
