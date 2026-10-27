'use client'

import { useState } from 'react'
import type { AppApiError } from '../lib/apiError'

type Props = {
  title: string
  message?: string
  error?: AppApiError | null
  onRetry?: () => void
}

export function ServiceErrorState({ title, message, error, onRetry }: Props) {
  const [showDetails, setShowDetails] = useState(false)
  const copy = message || error?.message || 'We could not load this section right now.'
  return (
    <div className="rounded-xl border border-rose-200/80 bg-rose-50/60 px-5 py-6 text-center">
      <h2 className="text-base font-semibold text-cloudera-navy">{title}</h2>
      <p className="mt-2 text-sm text-slate-600">{copy}</p>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
        {onRetry ? (
          <button type="button" className="btn-primary h-9 px-4 text-sm" onClick={onRetry}>
            Retry
          </button>
        ) : null}
        {error ? (
          <button
            type="button"
            className="text-sm font-semibold text-slate-600 underline-offset-2 hover:underline"
            onClick={() => setShowDetails(open => !open)}
          >
            {showDetails ? 'Hide technical details' : 'View technical details'}
          </button>
        ) : null}
      </div>
      {showDetails && error ? (
        <pre className="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white p-3 text-left text-xs text-slate-600">
          {`HTTP ${error.status || '—'}\nCode: ${error.code}${error.requestId ? `\nRequest: ${error.requestId}` : ''}`}
        </pre>
      ) : null}
    </div>
  )
}
