import { useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion, useIsPresent, useReducedMotion } from 'framer-motion'
import { useModalFocus } from '../hooks/useModalFocus'
import { motionEase, motionTiming } from '../lib/motion'

interface ModalProps {
  open: boolean
  onClose?: () => void
  labelledBy?: string
  label?: string
  placement?: 'center' | 'left' | 'right'
  className?: string
  children: ReactNode
}

function ModalSurface({ onClose, labelledBy, label, placement = 'center', className = '', children }: Omit<ModalProps, 'open'>) {
  const panelRef = useRef<HTMLDivElement>(null)
  const present = useIsPresent()
  const reduceMotion = useReducedMotion()
  useModalFocus(panelRef, present, onClose)
  const offset = reduceMotion ? 0 : placement === 'left' ? -16 : 16

  return (
    <motion.div
      data-overlay="true"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      transition={{ duration: motionTiming.content }}
      className={`fixed inset-0 z-[9000] flex bg-black/65 backdrop-blur-sm ${placement === 'center' ? 'items-center justify-center p-4' : placement === 'left' ? 'justify-start' : 'justify-end'}`}
      style={{ pointerEvents: present ? 'auto' : 'none' }}
      onMouseDown={event => { if (event.target === event.currentTarget) onClose?.() }}
    >
      <motion.div
        ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={labelledBy} aria-label={label} aria-hidden={!present} tabIndex={-1}
        initial={reduceMotion ? false : placement === 'center' ? { y: 8 } : { x: offset }}
        animate={{ x: 0, y: 0 }} exit={placement === 'center' ? { y: reduceMotion ? 0 : 8 } : { x: offset }}
        transition={{ duration: motionTiming.surface, ease: motionEase }}
        className={`modal-surface relative min-h-0 min-w-0 bg-bg-secondary text-text-primary shadow-2xl outline-none ${placement === 'center' ? 'max-h-[calc(100dvh-2rem)] rounded-lg border border-border' : 'h-full max-w-[min(420px,100vw)] border-x border-border'} ${className}`}
      >
        {children}
      </motion.div>
    </motion.div>
  )
}

export default function Modal({ open, ...props }: ModalProps) {
  return createPortal(<AnimatePresence>{open && <ModalSurface {...props} />}</AnimatePresence>, document.body)
}
