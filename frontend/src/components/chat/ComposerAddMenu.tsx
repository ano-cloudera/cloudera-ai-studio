'use client'

import { BookOpen, Plus, Upload } from 'lucide-react'
import { useEffect, useRef } from 'react'

type Props = {
  open: boolean
  onToggle: () => void
  onClose: () => void
  onUploadFiles: () => void
  onKnowledge: () => void
  uploadInputRef: React.RefObject<HTMLInputElement | null>
  onFilesSelected: (files: FileList | null) => void
  accept: string
}

export function ComposerAddMenu({
  open,
  onToggle,
  onClose,
  onUploadFiles,
  onKnowledge,
  uploadInputRef,
  onFilesSelected,
  accept,
}: Props) {
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDocClick(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) onClose()
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  return (
    <div className="relative shrink-0" ref={menuRef}>
      <button
        type="button"
        data-testid="chat-add-button"
        aria-label="Add context or files"
        aria-expanded={open}
        aria-haspopup="menu"
        className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
        onClick={onToggle}
      >
        <Plus size={18} />
      </button>
      <input
        ref={uploadInputRef}
        type="file"
        className="sr-only"
        multiple
        accept={accept}
        onChange={e => {
          onFilesSelected(e.target.files)
          e.target.value = ''
        }}
      />
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-50 mb-2 min-w-[200px] rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
            onClick={() => {
              onClose()
              onKnowledge()
            }}
          >
            <BookOpen size={16} className="text-cloudera-violet" />
            Knowledge
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
            onClick={() => {
              onClose()
              onUploadFiles()
            }}
          >
            <Upload size={16} className="text-cloudera-violet" />
            Upload files
          </button>
        </div>
      )}
    </div>
  )
}
