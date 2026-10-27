'use client'

import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'

type Props = {
  title: string
  children: React.ReactNode
  onClose: () => void
  closeOnOverlayClick?: boolean
  returnFocusRef?: React.RefObject<HTMLElement | null>
}

export function SimpleModal({
  title,
  children,
  onClose,
  closeOnOverlayClick = true,
  returnFocusRef,
}: Props) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const mounted = typeof document !== 'undefined'

  useEffect(() => {
    if (!mounted) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [mounted])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      returnFocusRef?.current?.focus()
    }
  }, [onClose, returnFocusRef])

  if (!mounted) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 p-4"
      role="presentation"
      onMouseDown={event => {
        if (!closeOnOverlayClick) return
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-[101] w-full max-w-lg rounded-xl bg-white p-5 shadow-xl outline-none"
        onMouseDown={event => event.stopPropagation()}
      >
        <h2 id={titleId} className="text-lg font-semibold text-cloudera-navy">
          {title}
        </h2>
        <div className="mt-4">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
