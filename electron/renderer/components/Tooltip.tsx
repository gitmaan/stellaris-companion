import { useState, useRef, useEffect, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'

interface TooltipProps {
  content: ReactNode
  children: ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
}

/**
 * Stellaris-styled tooltip component
 * Appears on hover with a subtle animation and cyan glow
 */
function Tooltip({ content, children, position = 'top', delay = 100 }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [style, setStyle] = useState<React.CSSProperties>({})
  const triggerRef = useRef<HTMLSpanElement>(null)
  const timeoutRef = useRef<NodeJS.Timeout>()

  const showTooltip = () => {
    timeoutRef.current = setTimeout(() => {
      if (triggerRef.current) {
        const rect = triggerRef.current.getBoundingClientRect()
        setStyle(calculateStyle(rect, position))
        setIsVisible(true)
      }
    }, delay)
  }

  const hideTooltip = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    setIsVisible(false)
  }

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        className="inline-flex"
      >
        {children}
      </span>
      {createPortal(
        <AnimatePresence>
          {isVisible && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.1 }}
              className="fixed z-[9999] pointer-events-none"
              style={style}
            >
              <div className="relative px-3 py-2 text-xs leading-relaxed text-text-primary bg-bg-tertiary border border-accent-cyan/40 rounded shadow-lg"
                style={{
                  boxShadow: '0 0 10px rgba(0, 212, 255, 0.2), 0 4px 12px rgba(0, 0, 0, 0.4)',
                  maxWidth: '200px',
                }}
              >
                {/* Corner accents */}
                <div className="absolute top-0 left-0 w-2 h-2 border-l border-t border-accent-cyan/60" />
                <div className="absolute top-0 right-0 w-2 h-2 border-r border-t border-accent-cyan/60" />
                <div className="absolute bottom-0 left-0 w-2 h-2 border-l border-b border-accent-cyan/60" />
                <div className="absolute bottom-0 right-0 w-2 h-2 border-r border-b border-accent-cyan/60" />

                {content}
              </div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  )
}

function calculateStyle(
  rect: DOMRect,
  position: 'top' | 'bottom' | 'left' | 'right'
): React.CSSProperties {
  const offset = 8
  const viewportWidth = window.innerWidth

  switch (position) {
    case 'top':
      return {
        left: rect.left + rect.width / 2,
        top: rect.top - offset,
        transform: 'translate(-50%, -100%)',
      }
    case 'bottom':
      return {
        left: rect.left + rect.width / 2,
        top: rect.bottom + offset,
        transform: 'translate(-50%, 0)',
      }
    case 'left':
      // Position tooltip to the LEFT of trigger, with its right edge at trigger's left edge
      return {
        right: viewportWidth - rect.left + offset,
        top: rect.top + rect.height / 2,
        transform: 'translateY(-50%)',
      }
    case 'right':
      return {
        left: rect.right + offset,
        top: rect.top + rect.height / 2,
        transform: 'translateY(-50%)',
      }
  }
}

export default Tooltip
