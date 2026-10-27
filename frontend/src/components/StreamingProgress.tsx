'use client'

import { AssistantContent } from './ConversationInner'
import { ProgressStepsPanel, type ProgressStepsPanelProps } from './ProgressStepsPanel'

export function StreamingProgress(props: ProgressStepsPanelProps) {
  return (
    <AssistantContent>
      <div
        className="rounded-xl border border-slate-200/90 bg-white px-4 py-3 shadow-sm"
        role="status"
        aria-live="polite"
        aria-label="Analysis progress"
      >
        <ProgressStepsPanel {...props} />
      </div>
    </AssistantContent>
  )
}
