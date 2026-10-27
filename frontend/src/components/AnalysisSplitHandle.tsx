'use client'

import { useCallback, useRef } from 'react'

type Props = {
  onResizeStart: (clientX: number) => void
  onResizeMove: (clientX: number) => void
  onResizeEnd: () => void
}

export function AnalysisSplitHandle({ onResizeStart, onResizeMove, onResizeEnd }: Props) {
  const dragging = useRef(false)

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      dragging.current = true
      onResizeStart(event.clientX)
      event.currentTarget.setPointerCapture(event.pointerId)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'

      const target = event.currentTarget

      const onMove = (ev: PointerEvent) => {
        if (!dragging.current) return
        ev.preventDefault()
        onResizeMove(ev.clientX)
      }

      const onUp = (ev: PointerEvent) => {
        dragging.current = false
        onResizeEnd()
        target.releasePointerCapture(ev.pointerId)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }

      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    },
    [onResizeEnd, onResizeMove, onResizeStart],
  )

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panels"
      onPointerDown={onPointerDown}
      className="group relative hidden w-3 shrink-0 cursor-col-resize select-none touch-none lg:block"
    >
      <div className="absolute inset-y-0 -left-2 -right-2 z-10" aria-hidden />
      <div className="mx-auto flex h-full w-full items-center justify-center">
        <div className="h-10 w-1 rounded-full bg-slate-300/90 transition-colors group-hover:bg-cloudera-orange/70 group-active:bg-cloudera-orange" />
      </div>
    </div>
  )
}
