import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { UIEvent } from 'react'
import { useTranslation } from 'react-i18next'

const ITEM_GAP_PX = 12
const ESTIMATED_ITEM_HEIGHT_PX = 92
const OVERSCAN_COUNT = 8
const STICKY_BOTTOM_THRESHOLD_PX = 80

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
  render: (ref: (el: HTMLDivElement | null) => void, animateEntrance: boolean) => JSX.Element
}

interface VirtualChatListProps {
  items: VirtualChatItem[]
  identityKey?: string
  isLoading?: boolean
  scrollToBottomSignal?: number
}

export default function VirtualChatList({ items, identityKey, scrollToBottomSignal }: VirtualChatListProps) {
  const { t } = useTranslation()
  const [atBottom, setAtBottom] = useState(true)
  const seenRef = useRef(new Set(items.map(item => item.key)))
  const anchorRef = useRef<{ key: string; offset: number } | null>(null)
  const offsetsRef = useRef<number[]>([])
  const itemsRef = useRef(items)
  itemsRef.current = items
  const containerRef = useRef<HTMLDivElement | null>(null)
  const nodesRef = useRef<Map<string, HTMLDivElement>>(new Map())
  const observersRef = useRef<Map<string, ResizeObserver>>(new Map())
  const pendingMeasureRef = useRef<Set<string>>(new Set())
  const rafRef = useRef<number | null>(null)
  const didInitialScrollRef = useRef(false)
  const isAtBottomRef = useRef(true)

  const heightsRef = useRef<Map<string, number>>(new Map())
  const [layoutVersion, setLayoutVersion] = useState(0)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportHeight, setViewportHeight] = useState(0)

  // If the list identity changes (e.g., session reset), clear cached measurements.
  const cacheIdentityKey = identityKey ?? (items.length > 0 ? items[0].key : 'empty')
  useLayoutEffect(() => {
    heightsRef.current = new Map()
    for (const key of nodesRef.current.keys()) pendingMeasureRef.current.add(key)
    scheduleMeasure()
    seenRef.current = new Set(itemsRef.current.map(item => item.key))
    anchorRef.current = null
    setAtBottom(true)
    setLayoutVersion(v => v + 1)
    didInitialScrollRef.current = false
    isAtBottomRef.current = true
  }, [cacheIdentityKey])

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    const el = containerRef.current
    if (!el) return
    const target = Math.max(0, el.scrollHeight - el.clientHeight)
    el.scrollTo({ top: target, behavior })
    setScrollTop(el.scrollTop)
  }, [])

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
    (index: string) => (node: HTMLDivElement | null) => {
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
    const distanceFromBottom = el.scrollHeight - el.clientHeight - el.scrollTop
    isAtBottomRef.current = distanceFromBottom <= STICKY_BOTTOM_THRESHOLD_PX
    setAtBottom(isAtBottomRef.current)
    const index = Math.min(itemsRef.current.length - 1, Math.max(0, lowerBound(offsetsRef.current, el.scrollTop) - 1))
    const item = itemsRef.current[index]
    if (item) anchorRef.current = { key: item.key, offset: el.scrollTop - (offsetsRef.current[index] ?? 0) }
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
      const h = heightsRef.current.get(items[i].key) ?? ESTIMATED_ITEM_HEIGHT_PX
      arr[i + 1] = arr[i] + h
    }
    return arr
  }, [items, layoutVersion])

  offsetsRef.current = offsets

  useLayoutEffect(() => {
    const el = containerRef.current, anchor = anchorRef.current
    if (!el || isAtBottomRef.current || !anchor) return
    const index = items.findIndex(item => item.key === anchor.key)
    if (index < 0) return
    el.scrollTop = offsets[index] + anchor.offset
    setScrollTop(el.scrollTop)
  }, [items, offsets])

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

  useLayoutEffect(() => {
    for (const item of items) seenRef.current.add(item.key)
  }, [items])

  // Best-practice chat behavior:
  // - Stick to bottom only if the user is already near the bottom.
  // - Always allow an explicit "scroll to bottom" signal (e.g., after sending a message).
  useLayoutEffect(() => {
    if (items.length === 0) return
    if (didInitialScrollRef.current) return
    didInitialScrollRef.current = true
    scrollToBottom('auto')
  }, [items.length, scrollToBottom])

  useLayoutEffect(() => {
    if (items.length === 0) return
    if (!isAtBottomRef.current) return
    scrollToBottom('auto')
  }, [items.length, layoutVersion, viewportHeight, scrollToBottom])

  useLayoutEffect(() => {
    if (scrollToBottomSignal === undefined) return
    isAtBottomRef.current = true
    scrollToBottom('auto')
  }, [scrollToBottomSignal, scrollToBottom])

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current)
      for (const ro of observersRef.current.values()) ro.disconnect()
    }
  }, [])

  return (
    <>
    <div ref={containerRef} data-chat-scroll className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col" style={{ overflowAnchor: 'none' }} onScroll={onScroll}>
      {topSpacer > 0 && <div style={{ height: topSpacer, flex: '0 0 auto' }} />}
      {endIndex >= startIndex &&
        items.slice(startIndex, endIndex + 1).map(item => {
          return item.render(setItemRef(item.key), !seenRef.current.has(item.key))
        })}
      {bottomSpacer > 0 && <div style={{ height: bottomSpacer, flex: '0 0 auto' }} />}
    </div>
    {!atBottom && <button type="button" onClick={() => { isAtBottomRef.current = true; setAtBottom(true); scrollToBottom() }} className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-accent-cyan/40 bg-bg-secondary px-4 py-2 text-sm text-accent-cyan shadow-lg">{t('visualQuality.jumpLatest')}</button>}
    </>
  )
}
