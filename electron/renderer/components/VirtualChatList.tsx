import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { UIEvent } from 'react'

const ITEM_GAP_PX = 12
const ESTIMATED_ITEM_HEIGHT_PX = 92
const OVERSCAN_COUNT = 8

function lowerBound(offsets: number[], value: number): number {
  let lo = 0
  let hi = offsets.length
  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if (offsets[mid] < value) lo = mid + 1
    else hi = mid
  }
  return lo
}

export interface VirtualChatItem {
  key: string
  render: (ref: (el: HTMLDivElement | null) => void) => JSX.Element
}

interface VirtualChatListProps {
  items: VirtualChatItem[]
  isLoading?: boolean
}

export default function VirtualChatList({ items }: VirtualChatListProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const nodesRef = useRef<Map<number, HTMLDivElement>>(new Map())
  const observersRef = useRef<Map<number, ResizeObserver>>(new Map())
  const pendingMeasureRef = useRef<Set<number>>(new Set())
  const rafRef = useRef<number | null>(null)

  const heightsRef = useRef<Map<number, number>>(new Map())
  const [layoutVersion, setLayoutVersion] = useState(0)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportHeight, setViewportHeight] = useState(0)

  // If the list identity changes (e.g., session reset), clear cached measurements.
  const identityKey = items.length > 0 ? items[0].key : 'empty'
  useEffect(() => {
    heightsRef.current = new Map()
    nodesRef.current = new Map()
    for (const ro of observersRef.current.values()) ro.disconnect()
    observersRef.current = new Map()
    pendingMeasureRef.current = new Set()
    setLayoutVersion(v => v + 1)
  }, [identityKey])

  const scheduleMeasure = useCallback(() => {
    if (rafRef.current !== null) return
    rafRef.current = window.requestAnimationFrame(() => {
      rafRef.current = null
      const pending = Array.from(pendingMeasureRef.current)
      pendingMeasureRef.current.clear()

      let changed = false
      for (const index of pending) {
        const node = nodesRef.current.get(index)
        if (!node) continue
        const measured = Math.max(1, node.offsetHeight + ITEM_GAP_PX)
        const prev = heightsRef.current.get(index)
        if (prev !== measured) {
          heightsRef.current.set(index, measured)
          changed = true
        }
      }
      if (changed) setLayoutVersion(v => v + 1)
    })
  }, [])

  const setItemRef = useCallback(
    (index: number) => (node: HTMLDivElement | null) => {
      const prevNode = nodesRef.current.get(index)
      if (prevNode === node) return

      const prevObserver = observersRef.current.get(index)
      if (prevObserver) {
        prevObserver.disconnect()
        observersRef.current.delete(index)
      }

      if (!node) {
        nodesRef.current.delete(index)
        return
      }

      nodesRef.current.set(index, node)
      pendingMeasureRef.current.add(index)
      scheduleMeasure()

      const ro = new ResizeObserver(() => {
        pendingMeasureRef.current.add(index)
        scheduleMeasure()
      })
      ro.observe(node)
      observersRef.current.set(index, ro)
    },
    [scheduleMeasure],
  )

  const onScroll = useCallback((e: UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    setScrollTop(el.scrollTop)
  }, [])

  // Track viewport height for range calculations.
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return

    const update = () => setViewportHeight(el.clientHeight)
    update()

    const ro = new ResizeObserver(() => update())
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const offsets = useMemo(() => {
    const count = items.length
    const arr = new Array<number>(count + 1)
    arr[0] = 0
    for (let i = 0; i < count; i++) {
      const h = heightsRef.current.get(i) ?? ESTIMATED_ITEM_HEIGHT_PX
      arr[i + 1] = arr[i] + h
    }
    return arr
  }, [items.length, layoutVersion])

  const totalHeight = offsets[offsets.length - 1] ?? 0

  const { startIndex, endIndex, topSpacer, bottomSpacer } = useMemo(() => {
    const count = items.length
    if (count === 0) {
      return { startIndex: 0, endIndex: -1, topSpacer: 0, bottomSpacer: 0 }
    }

    const viewTop = Math.max(0, scrollTop)
    const viewBottom = Math.max(viewTop, viewTop + viewportHeight)

    // offsets is length count+1; lowerBound returns in [0..count+1]
    const rawStart = Math.max(0, lowerBound(offsets, viewTop) - 1)
    const rawEnd = Math.max(rawStart, Math.min(count - 1, lowerBound(offsets, viewBottom) - 1))

    const start = Math.max(0, rawStart - OVERSCAN_COUNT)
    const end = Math.min(count - 1, rawEnd + OVERSCAN_COUNT)

    const top = offsets[start] ?? 0
    const bottom = Math.max(0, totalHeight - (offsets[end + 1] ?? totalHeight))

    return { startIndex: start, endIndex: end, topSpacer: top, bottomSpacer: bottom }
  }, [items.length, offsets, scrollTop, totalHeight, viewportHeight])

  // Preserve current behavior: always scroll to bottom when items change.
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const target = Math.max(0, totalHeight - viewportHeight)
    el.scrollTo({ top: target, behavior: 'smooth' })
  }, [items.length, totalHeight, viewportHeight])

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current)
      for (const ro of observersRef.current.values()) ro.disconnect()
    }
  }, [])

  return (
    <div ref={containerRef} className="chat-messages chat-messages-virtual" onScroll={onScroll}>
      {topSpacer > 0 && <div style={{ height: topSpacer, flex: '0 0 auto' }} />}
      {endIndex >= startIndex &&
        items.slice(startIndex, endIndex + 1).map((item, i) => {
          const index = startIndex + i
          return item.render(setItemRef(index))
        })}
      {bottomSpacer > 0 && <div style={{ height: bottomSpacer, flex: '0 0 auto' }} />}
    </div>
  )
}
