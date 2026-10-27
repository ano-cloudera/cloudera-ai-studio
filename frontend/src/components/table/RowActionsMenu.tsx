'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MoreHorizontal } from 'lucide-react'

export type RowMenuItem =
  | { key: string; label: string; danger?: boolean; onClick: () => void }
  | { key: string; separator: true }

type Props = {
  label: string
  items: RowMenuItem[]
  menuButtonRef?: React.RefObject<HTMLButtonElement | null>
}

export function RowActionsMenu({ label, items, menuButtonRef }: Props) {
  const [open, setOpen] = useState(false)
  const localRef = useRef<HTMLButtonElement>(null)
  const triggerRef = menuButtonRef ?? localRef
  const menuRef = useRef<HTMLUListElement>(null)
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null)

  const close = useCallback(() => setOpen(false), [])

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return
    const rect = triggerRef.current.getBoundingClientRect()
    const menuWidth = 176
    const estimatedHeight = Math.min(320, items.length * 40 + 8)
    let top = rect.bottom + 4
    let left = rect.right - menuWidth
    if (left < 8) left = 8
    if (top + estimatedHeight > window.innerHeight - 8) {
      top = Math.max(8, rect.top - estimatedHeight - 4)
    }
    setCoords({ top, left })
  }, [open, items.length, triggerRef])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, close])

  const menu =
    open && coords
      ? createPortal(
          <>
            <button
              type="button"
              className="fixed inset-0 z-[200] cursor-default bg-transparent"
              aria-label="Close menu"
              onClick={close}
            />
            <ul
              ref={menuRef}
              role="menu"
              className="fixed z-[210] min-w-[11rem] rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
              style={{ top: coords.top, left: coords.left }}
            >
              {items.map(item => {
                if ('separator' in item) {
                  return <li key={item.key} role="separator" className="my-1 border-t border-slate-100" />
                }
                return (
                  <li key={item.key} role="none">
                    <button
                      type="button"
                      role="menuitem"
                      className={`block w-full px-3 py-2 text-left ${
                        item.danger ? 'text-red-700 hover:bg-red-50' : 'text-cloudera-navy hover:bg-slate-50'
                      }`}
                      onClick={event => {
                        event.stopPropagation()
                        close()
                        item.onClick()
                      }}
                    >
                      {item.label}
                    </button>
                  </li>
                )
              })}
            </ul>
          </>,
          document.body,
        )
      : null

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        className="rounded-lg border border-slate-200 p-1.5 text-slate-600 hover:bg-slate-50"
        onClick={event => {
          event.stopPropagation()
          setOpen(v => !v)
        }}
      >
        <MoreHorizontal size={16} />
      </button>
      {menu}
    </>
  )
}
