'use client'

import { useState } from 'react'
import { ProgressStepsPanel } from './ProgressStepsPanel'
import { formatResponseMetadata } from '../lib/responseMetadata'
import type { ProcessSnapshot } from '../lib/chatSessions'
import type { ChatResponse } from '../types/api'

type ResponseFooterProps = {
  response: ChatResponse
  processSnapshot?: ProcessSnapshot
  /** Plain row under footnote (no extra card chrome). */
  variant?: 'card' | 'inline'
  metadataClassName?: string
}

export function ResponseFooter({ response, processSnapshot, variant = 'inline', metadataClassName = 'type-chat-meta' }: ResponseFooterProps) {
  const [processOpen, setProcessOpen] = useState(false)
  const metadata = formatResponseMetadata(response)

  const shellClass = variant === 'card' ? 'answer-surface-meta' : ''

  return (
    <div className={shellClass}>
      <div className={`${metadataClassName} flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
        <span>{metadata}</span>
        {processSnapshot && (
          <>
            <span className="text-slate-300" aria-hidden>
              ·
            </span>
            <button
              type="button"
              onClick={() => setProcessOpen(open => !open)}
              className="font-semibold text-cloudera-navy/80 hover:text-cloudera-navy"
              aria-expanded={processOpen}
            >
              {processOpen ? 'Hide process' : 'View process'}
            </button>
          </>
        )}
      </div>
      {processOpen && processSnapshot && (
        <div className="mt-3 rounded-lg border border-slate-200/90 bg-slate-50/60 px-3 py-3">
          <ProgressStepsPanel
            activeStepIndex={processSnapshot.activeStepIndex}
            technicalTrace={processSnapshot.technicalTrace}
            complete
            defaultViewLevel={2}
          />
        </div>
      )}
    </div>
  )
}
