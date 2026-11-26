import { api } from '../../lib/api'
import { isAppApiError } from '../../lib/apiError'

export type SuggestionItem = Record<string, unknown> & {
  suggestion_id?: string
  key?: string
  status?: string
}

export type DroppedSuggestion = { type: string; name: string; table?: string; expression?: string; reason: string }

export type SuggestionBucket = {
  entities?: SuggestionItem[]
  metrics?: SuggestionItem[]
  dimensions?: SuggestionItem[]
  relationships?: SuggestionItem[]
  glossary_suggestions?: SuggestionItem[]
  terms?: SuggestionItem[]
  /** Drafted by an AI model from the data (profiled, every metric run, joins checked). */
  drafted?: boolean
  /** No AI model was available: suggestions from column names only. */
  basic?: boolean
  provider?: string
  dropped?: DroppedSuggestion[]
  notes?: string[]
}

export type SemanticDraftJob = {
  job_id: string
  status: 'running' | 'done' | 'failed'
  stage: string
  elapsed_seconds: number
  result: SuggestionBucket | null
  error: string | null
}

export type SuggestionDecision = {
  suggestion_id: string
  type: string
  accepted: boolean
  payload: SuggestionItem
  edits: Record<string, string>
  editing: boolean
}

export const SUGGESTION_SECTIONS: Array<{ key: keyof SuggestionBucket; label: string; type: string }> = [
  { key: 'entities', label: 'Data Models', type: 'entity' },
  { key: 'metrics', label: 'Metrics', type: 'metric' },
  { key: 'dimensions', label: 'Dimensions', type: 'dimension' },
  { key: 'relationships', label: 'Relationships', type: 'relationship' },
  { key: 'glossary_suggestions', label: 'Glossary', type: 'term' },
]

export const DRAFT_LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'id', label: 'Bahasa Indonesia' },
] as const

const LANGUAGE_KEY = 'semanticDraftLanguage'

/** The language last chosen for drafted names and descriptions, remembered in this browser only. */
export function rememberedDraftLanguage(): string {
  try {
    const value = window.localStorage.getItem(LANGUAGE_KEY)
    return value === 'id' || value === 'en' ? value : 'en'
  } catch {
    return 'en'
  }
}

export function rememberDraftLanguage(value: string): void {
  try {
    window.localStorage.setItem(LANGUAGE_KEY, value)
  } catch {
    // Private mode or blocked storage: the choice simply is not remembered.
  }
}

export function labelForSuggestion(item: SuggestionItem): string {
  return String(item.name ?? item.term ?? item.key ?? 'Suggestion')
}

export function initSuggestionDecisions(
  bucket: SuggestionBucket,
  options?: { defaultAcceptedTypes?: Set<string> },
): Record<string, SuggestionDecision> {
  const defaultAccepted = options?.defaultAcceptedTypes
  const next: Record<string, SuggestionDecision> = {}
  for (const section of SUGGESTION_SECTIONS) {
    const items = (bucket[section.key] as SuggestionItem[] | undefined) ?? []
    for (const item of items) {
      const sid = String(item.suggestion_id ?? `${section.type}:${item.key ?? ''}`)
      const accepted = defaultAccepted ? defaultAccepted.has(section.type) : true
      next[sid] = {
        suggestion_id: sid,
        type: section.type,
        accepted,
        payload: item,
        edits: {},
        editing: false,
      }
    }
  }
  return next
}

export function selectionsFromDecisions(decisions: Record<string, SuggestionDecision>) {
  return Object.values(decisions).map(d => ({
    suggestion_id: d.suggestion_id,
    type: d.type,
    accepted: d.accepted,
    payload: { ...d.payload, ...d.edits },
    changes: d.edits,
  }))
}

/**
 * The draft names a table's data model after the table; when the data model was imported under another key, every suggestion
 * that points at it is pointed at the imported one.
 */
export function remapEntityKey(bucket: SuggestionBucket, from: string, to: string): SuggestionBucket {
  if (!from || !to || from === to) return bucket
  const swap = (value: unknown) => (value === from ? to : value)
  const point = (items?: SuggestionItem[]) =>
    items?.map(item => {
      const next: Record<string, unknown> = { ...item }
      for (const field of ['key', 'source_entity_key', 'from_entity_key', 'to_entity_key']) {
        if (field === 'key' && next.suggestion_id !== `entity:${from}`) continue
        if (field in next) next[field] = swap(next[field])
      }
      if (typeof next.join_expression === 'string') {
        next.join_expression = next.join_expression.replace(new RegExp(`(^|[^A-Za-z0-9_])${from}\\.`, 'g'), `$1${to}.`)
      }
      return next as SuggestionItem
    })
  return {
    ...bucket,
    entities: point(bucket.entities),
    metrics: point(bucket.metrics),
    dimensions: point(bucket.dimensions),
    relationships: point(bucket.relationships),
  }
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export class DraftCancelled extends Error {}

/**
 * Draft suggestions for the selected tables. The AI model drafts them from the data in a background job, reported through
 * `onStage`; when no AI model is available the platform's basic suggestions (from column names) are returned, marked `basic`.
 */
export async function draftSuggestions(
  body: { connection_id: string; tables: string[]; language?: string; context?: string },
  onStage: (stage: string) => void,
  options: { cancelled?: () => boolean; pollMs?: number } = {},
): Promise<SuggestionBucket> {
  const cancelled = options.cancelled ?? (() => false)
  let job: SemanticDraftJob
  try {
    job = await api.startSemanticDraft(body)
  } catch (err) {
    if (isAppApiError(err) && err.code === 'no_model') {
      const basic = (await api.semanticSuggestions({ connection_id: body.connection_id, tables: body.tables })) as SuggestionBucket
      return { ...basic, basic: true }
    }
    throw err
  }
  while (job.status === 'running') {
    onStage(job.stage)
    await sleep(options.pollMs ?? 1500)
    if (cancelled()) throw new DraftCancelled('cancelled')
    job = await api.getSemanticDraft(job.job_id)
  }
  if (job.status === 'failed' || !job.result) throw new Error(job.error || 'The draft failed.')
  return job.result
}
