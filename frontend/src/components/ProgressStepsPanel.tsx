'use client'

import { useState } from 'react'
import {
  DETAILED_PROGRESS_STEPS,
  SUMMARY_PROGRESS_PHASES,
  compactProgressLabel,
  detailedStepToSummaryPhase,
  type ProgressTraceEntry,
} from '../lib/streamProgress'

type ViewLevel = 1 | 2 | 3

export type ProgressStepsPanelProps = {
  activeStepIndex: number
  technicalTrace?: ProgressTraceEntry[]
  complete?: boolean
  /** When true, only show compact streaming line (no expand controls). */
  compactOnly?: boolean
  /** Initial panel depth when embedded under a response (skips compact header). */
  defaultViewLevel?: ViewLevel
}

function StepIcon({ state }: { state: 'done' | 'active' | 'pending' }) {
  if (state === 'done') return <span className="text-emerald-600" aria-hidden>✓</span>
  if (state === 'active') return <span className="progress-step-dot-active motion-reduce:opacity-100" aria-hidden />
  return <span className="text-slate-300" aria-hidden>○</span>
}

function ActiveEllipsis() {
  return (
    <span className="progress-step-ellipsis ml-0.5 inline-flex w-[1.1em] motion-reduce:opacity-70" aria-hidden>
      <span>.</span>
      <span>.</span>
      <span>.</span>
    </span>
  )
}

function stepState(index: number, activeIndex: number, complete: boolean): 'done' | 'active' | 'pending' {
  if (complete) return 'done'
  if (index < activeIndex) return 'done'
  if (index === activeIndex) return 'active'
  return 'pending'
}

function summaryPhaseState(phaseIndex: number, activeStepIndex: number, complete: boolean): 'done' | 'active' | 'pending' {
  const activePhase = complete ? SUMMARY_PROGRESS_PHASES.length : detailedStepToSummaryPhase(activeStepIndex)
  if (complete) return 'done'
  if (phaseIndex < activePhase) return 'done'
  if (phaseIndex === activePhase) return 'active'
  return 'pending'
}

export function ProgressStepsPanel({
  activeStepIndex,
  technicalTrace: _technicalTrace,
  complete = false,
  compactOnly = false,
  defaultViewLevel = 1,
}: ProgressStepsPanelProps) {
  const [viewLevel, setViewLevel] = useState<ViewLevel>(defaultViewLevel)
  const compactLabel = compactProgressLabel(activeStepIndex, complete)

  if (compactOnly) {
    return (
      <p className="type-chat-meta flex items-center gap-2 font-medium text-cloudera-navy">
        <span className="progress-step-dot-active motion-reduce:opacity-100" aria-hidden />
        <span>
          {compactLabel}
          <ActiveEllipsis />
        </span>
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {viewLevel === 1 && (
        <div className="space-y-2">
          <p className="type-chat-meta font-medium text-cloudera-navy">
            {complete ? (
              <>
                <span className="text-emerald-600">✓</span> {compactLabel}
              </>
            ) : (
              <span className="inline-flex items-center gap-2">
                <span className="progress-step-dot-active motion-reduce:opacity-100" aria-hidden />
                <span>
                  {compactLabel}
                  <ActiveEllipsis />
                </span>
              </span>
            )}
          </p>
          <button
            type="button"
            onClick={() => setViewLevel(2)}
            className="type-chat-meta font-semibold text-slate-500 hover:text-cloudera-navy"
          >
            {complete ? 'View process' : 'View details'}
          </button>
        </div>
      )}

      {viewLevel === 2 && (
        <>
          <ul className="type-chat-meta space-y-1.5 text-slate-600">
            {SUMMARY_PROGRESS_PHASES.map((phase, index) => {
              const state = summaryPhaseState(index, activeStepIndex, complete)
              return (
                <li key={phase} className={`flex items-center gap-2 ${state === 'pending' ? 'text-slate-400' : ''}`}>
                  <StepIcon state={state} />
                  <span className={state === 'active' ? 'font-medium text-slate-700' : ''}>
                    {phase}
                    {state === 'active' && !complete ? <ActiveEllipsis /> : null}
                  </span>
                </li>
              )
            })}
          </ul>
          <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-2">
            <button
              type="button"
              onClick={() => setViewLevel(3)}
              className="type-chat-meta font-semibold text-slate-500 hover:text-cloudera-navy"
            >
              View detailed steps
            </button>
            <button
              type="button"
              onClick={() => setViewLevel(1)}
              className="type-chat-meta font-semibold text-slate-500 hover:text-cloudera-navy"
            >
              Hide
            </button>
          </div>
        </>
      )}

      {viewLevel === 3 && (
        <>
          <ul className="type-chat-meta space-y-1.5 text-slate-600">
            {DETAILED_PROGRESS_STEPS.map((step, index) => {
              const state = stepState(index, activeStepIndex, complete)
              return (
                <li key={step} className={`flex items-center gap-2 ${state === 'pending' ? 'text-slate-400' : ''}`}>
                  <StepIcon state={state} />
                  <span className={state === 'active' ? 'font-medium text-slate-700' : ''}>
                    {step}
                    {state === 'active' && !complete ? <ActiveEllipsis /> : null}
                  </span>
                </li>
              )
            })}
          </ul>
          <div className="border-t border-slate-100 pt-2">
            <button
              type="button"
              onClick={() => setViewLevel(2)}
              className="type-chat-meta font-semibold text-slate-500 hover:text-cloudera-navy"
            >
              Back to summary
            </button>
          </div>
        </>
      )}
    </div>
  )
}
