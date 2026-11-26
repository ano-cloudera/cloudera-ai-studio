'use client'

import {
  labelForSuggestion,
  SUGGESTION_SECTIONS,
  type SuggestionBucket,
  type SuggestionDecision,
  type SuggestionItem,
} from './semanticSuggestionsUi'

type Props = {
  bucket: SuggestionBucket
  decisions: Record<string, SuggestionDecision>
  onDecision: (sid: string, patch: Partial<SuggestionDecision>) => void
  /** Which sections to show (the modal after an import leaves out Data Models). */
  types?: string[]
  editable?: boolean
  rejectLabel?: string
}

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

function formatValue(value: unknown, unit: unknown): string {
  const n = typeof value === 'number' ? value : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN
  if (!Number.isFinite(n)) return value === null || value === undefined ? 'no value' : String(value)
  const u = typeof unit === 'string' ? unit.trim() : ''
  if (u === 'percent') return `${number.format(n)}%`
  return u ? `${number.format(n)} ${u}` : number.format(n)
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && v.trim() !== '') : []
}

function evidenceOf(item: SuggestionItem): Record<string, unknown> {
  return item.evidence && typeof item.evidence === 'object' ? (item.evidence as Record<string, unknown>) : {}
}

/** What a reviewer needs to decide on one suggestion: what it is, how it is computed, and what the data said about it. */
function Detail({ type, item }: { type: string; item: SuggestionItem }) {
  const evidence = evidenceOf(item)
  if (type === 'metric') {
    const rows = typeof evidence.rows === 'number' ? evidence.rows : null
    const extension = ((item.metadata as Record<string, unknown> | undefined)?.reference_extension ?? {}) as Record<string, unknown>
    const better = item.better === 'up' ? 'Higher is better' : item.better === 'down' ? 'Lower is better' : null
    return (
      <div className="mt-1.5 space-y-1">
        <code className="block overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-700">
          {text(item.expression)}
        </code>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
          {'value' in evidence ? (
            <span data-testid="suggestion-metric-value">
              Ran on the data: <span className="font-semibold text-slate-700">{formatValue(evidence.value, item.unit)}</span>
              {rows !== null ? (evidence.whole_table ? ` (all ${number.format(rows)} rows)` : ` (first ${number.format(rows)} rows)`) : null}
            </span>
          ) : null}
          {better ? <span>{better}</span> : null}
          {typeof extension.headline === 'number' ? <span>Home overview #{extension.headline}</span> : null}
        </div>
      </div>
    )
  }
  if (type === 'dimension') {
    const examples = Array.isArray(evidence.examples) ? evidence.examples.map(String).slice(0, 4) : []
    return (
      <p className="mt-1 text-[11px] text-slate-500">
        Column <code className="font-mono text-slate-700">{text(item.source_column)}</code>
        {typeof evidence.distinct === 'number' ? ` · ${number.format(evidence.distinct)} values` : ''}
        {examples.length ? ` · e.g. ${examples.join(', ')}` : ''}
      </p>
    )
  }
  if (type === 'relationship') {
    return (
      <p className="mt-1 text-[11px] text-slate-500">
        <code className="font-mono text-slate-700">{text(item.join_expression)}</code>
        {typeof evidence.checked === 'number' ? ` · ${evidence.matched} of ${evidence.checked} sampled values match` : ''}
      </p>
    )
  }
  if (type === 'entity') {
    const source = [item.schema, item.table_name].filter(Boolean).join('.')
    return (
      <p className="mt-1 text-[11px] text-slate-500">
        <code className="font-mono text-slate-700">{source}</code>
        {typeof evidence.row_count === 'number' ? ` · ${number.format(evidence.row_count)} rows` : ''}
        {text(item.primary_key) ? ` · key ${text(item.primary_key)}` : ''}
      </p>
    )
  }
  return null
}

export function SuggestionReview({ bucket, decisions, onDecision, types, editable = false, rejectLabel = 'Reject' }: Props) {
  const sections = SUGGESTION_SECTIONS.filter(s => !types || types.includes(s.type))
  const dropped = bucket.dropped ?? []
  const notes = bucket.notes ?? []
  return (
    <div className="space-y-3 text-sm" data-testid="suggestion-review">
      {bucket.drafted ? (
        <p className="text-xs text-slate-600" data-testid="suggestion-review-source">
          Drafted by <span className="font-semibold">{bucket.provider || 'the AI model'}</span> from your data. Every metric below ran on
          the data and every join was checked against it. Review, edit or reject before you finish; nothing is published.
        </p>
      ) : null}
      {bucket.basic ? (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="suggestion-review-basic">
          No AI model is available, so these are basic suggestions from column names. Assign a model to Ask Data in Settings → AI
          Models to get a draft written from your data.
        </p>
      ) : null}

      {sections.map(section => {
        const items = (bucket[section.key] as SuggestionItem[] | undefined) ?? []
        if (!items.length) return null
        return (
          <div key={section.key} className="rounded-lg border border-slate-100 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">
              {section.label} <span className="font-normal normal-case text-slate-400">({items.length})</span>
            </div>
            <ul className="mt-2 space-y-2">
              {items.map(item => {
                const sid = String(item.suggestion_id ?? `${section.type}:${item.key}`)
                const d = decisions[sid]
                if (!d) return null
                const shown = { ...item, ...d.edits }
                const description = text(shown.description) || text(shown.definition)
                const synonyms = list(item.synonyms)
                return (
                  <li key={sid} className={`rounded border px-2.5 py-2 ${d.accepted ? 'border-slate-100' : 'border-slate-100 bg-slate-50 opacity-70'}`}>
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <span className="font-medium text-cloudera-navy">{labelForSuggestion(shown)}</span>
                      <div className="flex gap-2">
                        {editable ? (
                          <button type="button" className="text-xs text-slate-700" onClick={() => onDecision(sid, { editing: !d.editing })}>
                            Edit
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className={`text-xs ${d.accepted ? 'font-semibold text-emerald-700' : 'text-slate-500'}`}
                          onClick={() => onDecision(sid, { accepted: true })}
                        >
                          Accept
                        </button>
                        <button
                          type="button"
                          className={`text-xs ${!d.accepted ? 'font-semibold text-red-700' : 'text-slate-500'}`}
                          onClick={() => onDecision(sid, { accepted: false })}
                        >
                          {rejectLabel}
                        </button>
                      </div>
                    </div>
                    {d.editing ? (
                      <div className="mt-2 space-y-1.5">
                        <input
                          aria-label="Name"
                          className="w-full rounded border border-slate-200 px-2 py-1 text-sm"
                          value={d.edits.name ?? labelForSuggestion(item)}
                          onChange={e => onDecision(sid, { edits: { ...d.edits, name: e.target.value } })}
                        />
                        {section.type !== 'relationship' ? (
                          <textarea
                            aria-label="Description"
                            rows={2}
                            className="w-full rounded border border-slate-200 px-2 py-1 text-xs"
                            value={d.edits[section.type === 'term' ? 'definition' : 'description'] ?? description}
                            onChange={e =>
                              onDecision(sid, {
                                edits: {
                                  ...d.edits,
                                  [section.type === 'term' ? 'definition' : 'description']: e.target.value,
                                  ...(section.type === 'metric' ? { business_definition: e.target.value } : {}),
                                },
                              })
                            }
                          />
                        ) : null}
                      </div>
                    ) : description ? (
                      <p className="mt-0.5 text-xs text-slate-600">{description}</p>
                    ) : null}
                    <Detail type={section.type} item={item} />
                    {synonyms.length ? <p className="mt-1 text-[11px] text-slate-400">Also: {synonyms.join(', ')}</p> : null}
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}

      {dropped.length ? (
        <details className="rounded-lg border border-slate-100 p-3 text-xs" data-testid="suggestion-review-dropped">
          <summary className="cursor-pointer font-semibold text-slate-600">
            {dropped.length} suggestion(s) left out by the checks
          </summary>
          <ul className="mt-2 space-y-1.5 text-slate-600">
            {dropped.map((d, i) => (
              <li key={`${d.type}-${d.name}-${i}`}>
                <span className="font-medium text-slate-700">{d.name}</span>
                <span className="text-slate-400"> ({d.type}{d.table ? `, ${d.table}` : ''})</span>: {d.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {notes.length ? (
        <ul className="space-y-0.5 text-[11px] text-slate-500" data-testid="suggestion-review-notes">
          {notes.map(note => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
