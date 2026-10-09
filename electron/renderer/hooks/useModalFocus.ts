import { useLayoutEffect, useRef, type RefObject } from 'react'
import { isCompositionKey } from '../lib/compositionKey'

interface Layer {
  element: HTMLElement
  previous: HTMLElement | null
}

// Portals can overlap (for example, a report opened from another dialog).
// Only the top surface owns focus; preserve pre-existing inert attributes.
const layers: Layer[] = []
const background = new Map<HTMLElement, boolean>()
const topLayer = () => layers[layers.length - 1]
let pointerTrigger: HTMLElement | null = null
// macOS can activate a button without focusing it. Remember that invoker too,
// while keyboard activation continues to restore the actual focused element.
document.addEventListener('pointerdown', event => {
  pointerTrigger = event.target instanceof Element
    ? event.target.closest<HTMLElement>('button, a[href], [role="button"]') : null
}, true)
document.addEventListener('keydown', () => { pointerTrigger = null }, true)

function syncBackground() {
  const top = topLayer()?.element
  for (const [element, wasInert] of background) {
    element.inert = wasInert
  }
  background.clear()
  if (!top) return
  for (const element of Array.from(document.body.children)) {
    if (!(element instanceof HTMLElement) || element.contains(top) || element.hasAttribute('data-notifications')) continue
    background.set(element, element.inert)
    element.inert = true
  }
}

function focusableElements(element: HTMLElement) {
  // Actionable notices (such as Undo) remain reachable while a modal is open.
  const selector = 'button, a[href], input, select, textarea, summary, [tabindex]'
  const notices = document.querySelector('[data-notifications]')
  return [...Array.from(element.querySelectorAll<HTMLElement>(selector)), ...Array.from(notices?.querySelectorAll<HTMLElement>(selector) ?? [])]
    .filter(node => node.tabIndex >= 0 && !node.matches(':disabled') && !node.closest('[inert], [hidden], [aria-hidden="true"]')
      && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden')
}

export function useModalFocus<T extends HTMLElement>(
  ref: RefObject<T>,
  open: boolean,
  onClose?: () => void,
) {
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useLayoutEffect(() => {
    const element = ref.current
    if (!open || !element) return
    const previous = pointerTrigger?.isConnected && !pointerTrigger.closest('[inert]')
      ? pointerTrigger : document.activeElement instanceof HTMLElement ? document.activeElement : null
    pointerTrigger = null
    const layer = { element, previous }
    layers.push(layer)
    syncBackground()
    const focusStart = () => (element.querySelector<HTMLElement>('[data-modal-autofocus]:not(:disabled)') || element).focus({ preventScroll: true })
    focusStart()

    const onKeyDown = (event: KeyboardEvent) => {
      if (topLayer() !== layer || event.defaultPrevented || isCompositionKey(event)) return
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        closeRef.current?.()
      } else if (event.key === 'Tab') {
        const nodes = focusableElements(element)
        const first = nodes[0], last = nodes[nodes.length - 1]
        if (!first) { event.preventDefault(); focusStart(); return }
        const active = document.activeElement
        if (event.shiftKey && (active === first || !nodes.includes(active as HTMLElement))) {
          event.preventDefault(); last?.focus()
        } else if (!event.shiftKey && (active === last || !nodes.includes(active as HTMLElement))) {
          event.preventDefault(); first.focus()
        }
      }
    }
    const onFocus = (event: FocusEvent) => {
      if (topLayer() === layer && !element.contains(event.target as Node) && !(event.target as HTMLElement).closest('[data-notifications]')) focusStart()
    }
    const observer = new MutationObserver(syncBackground)
    observer.observe(document.body, { childList: true })
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('focusin', onFocus, true)
    return () => {
      observer.disconnect()
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('focusin', onFocus, true)
      const wasTop = topLayer() === layer
      const index = layers.indexOf(layer)
      if (index >= 0) layers.splice(index, 1)
      syncBackground()
      if (wasTop) {
        const target = layer.previous?.isConnected && !layer.previous.closest('[inert]') ? layer.previous : topLayer()?.element
        const nextLayer = topLayer()
        // React restores selection after layout-effect cleanup. Return focus
        // after that commit, unless another dialog has since taken ownership.
        queueMicrotask(() => {
          if (topLayer() === nextLayer && target?.isConnected && !target.closest('[inert]')) {
            target.focus({ preventScroll: true })
          }
        })
      }
    }
  }, [open, ref])
}
