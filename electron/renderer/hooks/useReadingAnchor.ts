import { useLayoutEffect, type RefObject } from 'react'

/** Preserve the paragraph being read when a window or text-size change reflows it. */
export function useReadingAnchor(ref: RefObject<HTMLElement>, identity: string | null) {
  useLayoutEffect(() => {
    const container = ref.current
    if (!container) return
    let width = container.clientWidth
    let anchor: { element: HTMLElement; fraction: number } | null = null
    const capture = () => {
      const top = container.getBoundingClientRect().top + 12
      const elements = Array.from(container.querySelectorAll<HTMLElement>('.chronicle-narrative > p, [data-reading-id]'))
      const element = elements.find(item => {
        const rect = item.getBoundingClientRect()
        return rect.top <= top && rect.bottom > top && !item.hasAttribute('data-reading-id')
      }) || elements.find(item => item.getBoundingClientRect().bottom > top)
      anchor = element ? { element, fraction: (top - element.getBoundingClientRect().top) / Math.max(1, element.offsetHeight) } : null
    }
    const observer = new ResizeObserver(() => {
      const nextWidth = container.clientWidth
      if (nextWidth !== width && anchor?.element.isConnected && container.scrollTop > 0) {
        container.scrollTop += anchor.element.getBoundingClientRect().top - container.getBoundingClientRect().top
          + anchor.fraction * anchor.element.offsetHeight - 12
      }
      width = nextWidth
      capture()
    })
    container.addEventListener('scroll', capture, { passive: true })
    observer.observe(container)
    capture()
    return () => { observer.disconnect(); container.removeEventListener('scroll', capture) }
  }, [ref, identity])
}
