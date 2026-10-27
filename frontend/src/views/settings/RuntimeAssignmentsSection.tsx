'use client'

import {
  assignmentHealthMessage,
  assignmentSourceLabel,
  CAPABILITY_GROUPS,
  CAPABILITY_ROWS,
  modelTypeLabel,
  modelsLikelyWrongTypeForCapability,
} from '../../lib/aiRegistryUi'
import type { AiModelRecord, AssignmentCapability, ModelAssignmentRecord } from '../../types/api'

type Props = {
  models: AiModelRecord[]
  assignmentByCap: Map<AssignmentCapability, ModelAssignmentRecord>
  onAssign: (capability: AssignmentCapability, modelId: string) => void | Promise<void>
  onClear: (capability: AssignmentCapability) => void
}

function AssignmentSourceBadge({ source }: { source: ModelAssignmentRecord['source'] }) {
  if (source === 'PROJECT') {
    return (
      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
        Project
      </span>
    )
  }
  if (source === 'WORKSPACE') {
    return (
      <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-800">
        Workspace
      </span>
    )
  }
  return (
    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
      Environment
    </span>
  )
}

export function RuntimeAssignmentsSection({ models, assignmentByCap, onAssign, onClear }: Props) {
  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-cloudera-navy">Runtime assignments</h3>
        <p className="type-chat-meta mt-1 max-w-2xl text-slate-500">
          Choose registered models for each capability. Chat capabilities are fully wired; embedding and reranker
          assignments are stored in the registry while the live pipeline still reads environment variables.
        </p>
      </div>

      {CAPABILITY_GROUPS.map(group => {
        const rows = CAPABILITY_ROWS.filter(r => r.group === group.id)
        return (
          <div key={group.id} className="space-y-2">
            <div className="px-0.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{group.title}</p>
              <p className="type-chat-meta mt-0.5 text-slate-500">{group.blurb}</p>
            </div>
            <ul className="space-y-2">
              {rows.map(row => {
                const effective = assignmentByCap.get(row.capability)
                const compatible = models.filter(m => m.model_type === row.modelType && m.enabled)
                const wrongType = modelsLikelyWrongTypeForCapability(models, row.modelType)
                const healthMsg = effective ? assignmentHealthMessage(effective) : null
                const hasRegistryModel =
                  effective?.model_name && effective.source !== 'LEGACY_FALLBACK'
                const source = effective?.source ?? 'LEGACY_FALLBACK'

                return (
                  <li
                    key={row.capability}
                    className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm"
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0 flex-1 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-sm font-semibold text-cloudera-navy">{row.label}</h4>
                          {row.optional ? (
                            <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                              Optional
                            </span>
                          ) : null}
                          <AssignmentSourceBadge source={source} />
                        </div>

                        <p className="text-sm text-slate-800">
                          {hasRegistryModel ? (
                            <span className="font-medium text-cloudera-navy">{effective!.model_name}</span>
                          ) : row.optional ? (
                            <span className="text-slate-600">No override — uses environment defaults</span>
                          ) : row.envBacked ? (
                            <span className="text-slate-600">No registry model — uses environment configuration</span>
                          ) : (
                            <span className="text-slate-600">No registry model assigned</span>
                          )}
                        </p>

                        {hasRegistryModel ? (
                          <p className="type-chat-meta text-slate-500">{assignmentSourceLabel(source)}</p>
                        ) : null}

                        <p className="type-chat-meta text-slate-500">{row.description}</p>

                        {wrongType.length > 0 ? (
                          <p className="text-xs text-amber-800">
                            {wrongType.map(m => m.name).join(', ')}{' '}
                            {wrongType.length === 1 ? 'is' : 'are'} registered as{' '}
                            {wrongType.length === 1 ? 'the wrong type' : 'the wrong types'} — re-register with type{' '}
                            {modelTypeLabel(row.modelType)} to enable assignment.
                          </p>
                        ) : compatible.length === 0 ? (
                          <p className="text-xs text-amber-800">
                            No enabled {modelTypeLabel(row.modelType)} models in the registry yet.
                          </p>
                        ) : null}

                        {healthMsg ? (
                          <p className="text-xs font-semibold text-rose-700" role="alert">
                            {healthMsg}
                          </p>
                        ) : null}
                      </div>

                      <div className="flex shrink-0 flex-col gap-1.5 sm:min-w-[12.5rem] sm:items-stretch">
                        {compatible.length > 0 ? (
                          <select
                            aria-label={`Assign model for ${row.label}`}
                            className="input w-full py-1.5 text-sm"
                            value=""
                            onChange={e => {
                              const id = e.target.value
                              if (id) void onAssign(row.capability, id)
                              e.target.value = ''
                            }}
                          >
                            <option value="">Change assignment…</option>
                            {compatible.map(m => (
                              <option key={m.id} value={m.id}>
                                {m.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <div
                            className="input flex w-full cursor-default items-center py-1.5 text-sm text-slate-500"
                            aria-label={`No ${modelTypeLabel(row.modelType)} models available for ${row.label}`}
                          >
                            No {modelTypeLabel(row.modelType)} models
                          </div>
                        )}
                        {effective?.source === 'PROJECT' ? (
                          <button
                            type="button"
                            className="text-left text-xs font-medium text-slate-600 underline decoration-slate-300 underline-offset-2 hover:text-cloudera-navy sm:text-right"
                            onClick={() => onClear(row.capability)}
                          >
                            Remove project assignment
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
    </section>
  )
}
