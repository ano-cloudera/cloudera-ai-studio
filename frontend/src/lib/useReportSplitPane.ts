'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'tempo-report-left-width-px'
const DEFAULT_CHAT_RATIO = 0.58
const MIN_LEFT_PX = 420
const MIN_RIGHT_PX = 420
const HANDLE_PX = 8
const CHAT_WIDTH_VAR = '--split-chat-width'

function clampLeft(px: number, containerWidth: number) {
  const maxLeft = Math.max(MIN_LEFT_PX, containerWidth - MIN_RIGHT_PX - HANDLE_PX)
  return Math.min(maxLeft, Math.max(MIN_LEFT_PX, px))
}

function readStoredLeftPx(containerWidth: number): number {
  if (typeof window === 'undefined') return containerWidth * DEFAULT_CHAT_RATIO
  const raw = sessionStorage.getItem(STORAGE_KEY)
  if (raw?.endsWith('px')) {
    const n = Number(raw.replace('px', ''))
    if (Number.isFinite(n)) return clampLeft(n, containerWidth)
  }
  const legacy = sessionStorage.getItem('tempo-report-pane-percent')
  if (legacy) {
    const pct = Number(legacy)
    if (Number.isFinite(pct)) return clampLeft(containerWidth * ((100 - pct) / 100), containerWidth)
  }
  return clampLeft(containerWidth * DEFAULT_CHAT_RATIO, containerWidth)
}

export function useReportSplitPane(layoutActive: boolean) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chatColumnRef = useRef<HTMLDivElement>(null)
  const [leftWidthPx, setLeftWidthPx] = useState<number | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragRef = useRef<{ startX: number; initialLeft: number } | null>(null)
  const liveWidthRef = useRef<number | null>(null)

  const applyChatWidth = useCallback((px: number) => {
    const container = containerRef.current
    const chat = chatColumnRef.current
    if (container) container.style.setProperty(CHAT_WIDTH_VAR, `${px}px`)
    if (chat) chat.style.width = `${px}px`
    liveWidthRef.current = px
  }, [])

  useEffect(() => {
    if (!layoutActive) return
    const measure = () => {
      const w = containerRef.current?.getBoundingClientRect().width
      if (!w) return
      const next = readStoredLeftPx(w)
      setLeftWidthPx(next)
      applyChatWidth(next)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [layoutActive, applyChatWidth])

  const beginResize = useCallback(
    (clientX: number) => {
      const chat = chatColumnRef.current
      if (!chat) return
      setIsDragging(true)
      dragRef.current = {
        startX: clientX,
        initialLeft: chat.getBoundingClientRect().width,
      }
    },
    [],
  )

  const moveResize = useCallback(
    (clientX: number) => {
      const drag = dragRef.current
      const container = containerRef.current
      if (!drag || !container) return
      const containerW = container.getBoundingClientRect().width
      const deltaX = clientX - drag.startX
      const next = clampLeft(drag.initialLeft + deltaX, containerW)
      applyChatWidth(next)
    },
    [applyChatWidth],
  )

  const endResize = useCallback(() => {
    dragRef.current = null
    setIsDragging(false)
    const finalWidth = liveWidthRef.current
    if (finalWidth != null) {
      setLeftWidthPx(finalWidth)
      sessionStorage.setItem(STORAGE_KEY, `${Math.round(finalWidth)}px`)
    }
  }, [])

  const chatStyle =
    layoutActive && leftWidthPx != null
      ? ({
          width: leftWidthPx,
          flex: '0 0 auto',
          minWidth: 0,
        } as const)
      : undefined

  const paneStyle =
    layoutActive && leftWidthPx != null
      ? ({
          flex: '1 1 0',
          minWidth: 0,
        } as const)
      : undefined

  return {
    containerRef,
    chatColumnRef,
    beginResize,
    moveResize,
    endResize,
    isDragging,
    chatStyle,
    paneStyle,
  }
}
