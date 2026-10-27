'use client'

import { BookOpen, FileText, X } from 'lucide-react'
import type { ChatContextSource } from '../../lib/chatContext'
import { contextSourceChipLabel } from '../../lib/chatContext'
import { attachmentStatusLabel, type ChatAttachmentStatus } from '../../lib/chatAttachments'

type Props = {
  sources: ChatContextSource[]
  onRemove: (id: string) => void
  onRetryAttachment?: (id: string) => void
  onSaveToKnowledge?: (id: string, name: string) => void
}

export function AttachedContextChips({ sources, onRemove, onRetryAttachment, onSaveToKnowledge }: Props) {
  if (!sources.length) return null
  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {sources.map(source => {
        const isFile = source.type === 'uploaded_file'
        const status = (source.metadata?.status as ChatAttachmentStatus | undefined) ?? undefined
        const sub = isFile ? attachmentStatusLabel(status) : null
        return (
          <span
            key={source.id}
            className="inline-flex max-w-full items-center gap-1 rounded-full border border-cloudera-violet/30 bg-white px-2.5 py-1 text-xs font-semibold text-cloudera-navy"
          >
            {isFile ? (
              <FileText size={12} className="shrink-0 text-cloudera-violet" aria-hidden />
            ) : (
              <BookOpen size={12} className="shrink-0 text-cloudera-violet" aria-hidden />
            )}
            <span className="truncate">{contextSourceChipLabel(source)}</span>
            {sub && <span className="font-normal text-slate-500">{sub}</span>}
            {isFile && status === 'READY' && onSaveToKnowledge && (
              <button
                type="button"
                className="text-cloudera-violet underline"
                onClick={() => onSaveToKnowledge(source.id, source.name)}
              >
                Save to Knowledge
              </button>
            )}
            {isFile && status === 'FAILED' && onRetryAttachment && (
              <button
                type="button"
                className="text-cloudera-violet underline"
                onClick={() => onRetryAttachment(source.id)}
              >
                Retry
              </button>
            )}
            <button
              type="button"
              aria-label={`Remove ${source.name} context`}
              className="rounded-full p-0.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => onRemove(source.id)}
            >
              <X size={12} />
            </button>
          </span>
        )
      })}
    </div>
  )
}
