'use client'

import { useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { ProgressStepsPanel } from './ProgressStepsPanel'
import { formatResponseMetadata } from '../lib/responseMetadata'
import { api } from '../lib/api'
import type { ProcessSnapshot } from '../lib/chatSessions'
import type { ChatResponse } from '../types/api'

type ResponseFooterProps = {
  response: ChatResponse
  processSnapshot?: ProcessSnapshot
  sessionId?: string
  /** Plain row under footnote (no extra card chrome). */
  variant?: 'card' | 'inline'
  metadataClassName?: string
  /** Hide model/timing/token line (executive tier). */
  hideTelemetry?: boolean
  /** Show thumbs up/down (Ask Data quality signal). */
  enableFeedback?: boolean
}

export function ResponseFooter({
  response,
  processSnapshot,
  sessionId,
  variant = 'inline',
  metadataClassName = 'type-chat-meta',
  hideTelemetry = false,
  enableFeedback = false,
}: ResponseFooterProps) {
  const [processOpen, setProcessOpen] = useState(false)
  const [feedbackSent, setFeedbackSent] = useState<'up' | 'down' | null>(null)
  const metadata = hideTelemetry ? null : formatResponseMetadata(response)

  const sendFeedback = (rating: 'up' | 'down') => {
    if (!enableFeedback || !sessionId || feedbackSent || response.status !== 'SUCCESS') return
    setFeedbackSent(rating)
    void api.postAskDataFeedback({
      request_id: response.request_id,
      session_id: sessionId,
      rating,
    })
  }

  const shellClass = variant === 'card' ? 'answer-surface-meta' : ''

  return (
    <div className={shellClass}>
      <div className={`${metadataClassName} flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
        {metadata ? <span>{metadata}</span> : null}
        {processSnapshot && (
          <>
            {metadata ? (
              <span className="text-slate-300" aria-hidden>
                ·
              </span>
            ) : null}
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
        {enableFeedback && response.status === 'SUCCESS' ? (
          <>
            {(metadata || processSnapshot) ? (
              <span className="text-slate-300" aria-hidden>
                ·
              </span>
            ) : null}
            <span className="inline-flex items-center gap-1" role="group" aria-label="Rate this answer">
              <button
                type="button"
                disabled={feedbackSent !== null}
                onClick={() => sendFeedback('up')}
                className={`rounded p-0.5 ${feedbackSent === 'up' ? 'text-emerald-600' : 'text-slate-400 hover:text-emerald-600'}`}
                aria-pressed={feedbackSent === 'up'}
                aria-label="Helpful"
              >
                <ThumbsUp size={14} aria-hidden />
              </button>
              <button
                type="button"
                disabled={feedbackSent !== null}
                onClick={() => sendFeedback('down')}
                className={`rounded p-0.5 ${feedbackSent === 'down' ? 'text-rose-600' : 'text-slate-400 hover:text-rose-600'}`}
                aria-pressed={feedbackSent === 'down'}
                aria-label="Not helpful"
              >
                <ThumbsDown size={14} aria-hidden />
              </button>
            </span>
          </>
        ) : null}
      </div>
      {processOpen && processSnapshot && (
        <div className="mt-3 rounded-lg border border-slate-200/90 bg-slate-50/60 px-3 py-3">
          <ProgressStepsPanel
            activeStepIndex={processSnapshot.activeStepIndex}
            technicalTrace={processSnapshot.technicalTrace}
            complete
            defaultViewLevel={3}
          />
        </div>
      )}
    </div>
  )
}
