export type SuggestionItem = Record<string, unknown> & {
  suggestion_id?: string
  key?: string
  status?: string
}

export type SuggestionBucket = {
  entities?: SuggestionItem[]
  metrics?: SuggestionItem[]
  dimensions?: SuggestionItem[]
  relationships?: SuggestionItem[]
  glossary_suggestions?: SuggestionItem[]
  terms?: SuggestionItem[]
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
