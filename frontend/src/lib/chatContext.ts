export type ChatContextSourceType =
  | 'knowledge_library'
  | 'uploaded_file'
  | 'mcp_connector'
  | 'table'
  | 'semantic_model'
  | 'semantic_entity'
  | 'semantic_metric'
  | 'semantic_term'

export type ChatContextSource = {
  type: ChatContextSourceType
  id: string
  name: string
  metadata?: Record<string, unknown>
}

export const PENDING_CHAT_CONTEXT_KEY = 'cai.pending_chat_context'

const STRUCTURED_TYPES: ChatContextSourceType[] = [
  'table',
  'semantic_model',
  'semantic_entity',
  'semantic_metric',
  'semantic_term',
]

export function knowledgeLibraryContext(library: { id: string; name: string }): ChatContextSource {
  return { type: 'knowledge_library', id: library.id, name: library.name }
}

export function uploadedFileContext(attachment: { id: string; name: string }): ChatContextSource {
  return { type: 'uploaded_file', id: attachment.id, name: attachment.name }
}

export function structuredContextSource(option: {
  type: ChatContextSourceType
  id: string
  name: string
  metadata?: Record<string, unknown>
}): ChatContextSource {
  return { type: option.type, id: option.id, name: option.name, metadata: option.metadata }
}

export function contextSourceChipLabel(source: ChatContextSource): string {
  switch (source.type) {
    case 'table':
      return `@Table: ${source.name}`
    case 'semantic_metric':
      return `@Metric: ${source.name}`
    case 'semantic_model':
      return `@Semantic: ${source.name}`
    case 'semantic_entity':
      return `@Entity: ${source.name}`
    case 'semantic_term':
      return `@Term: ${source.name}`
    case 'knowledge_library':
      return source.name
    case 'mcp_connector':
      return `@MCP: ${source.name}`
    default:
      return source.name
  }
}

export function setPendingChatContext(sources: ChatContextSource[]): void {
  if (typeof sessionStorage === 'undefined') return
  sessionStorage.setItem(PENDING_CHAT_CONTEXT_KEY, JSON.stringify(sources))
}

export function consumePendingChatContext(): ChatContextSource[] | null {
  if (typeof sessionStorage === 'undefined') return null
  const raw = sessionStorage.getItem(PENDING_CHAT_CONTEXT_KEY)
  if (!raw) return null
  sessionStorage.removeItem(PENDING_CHAT_CONTEXT_KEY)
  try {
    const parsed = JSON.parse(raw) as ChatContextSource[]
    if (!Array.isArray(parsed)) return null
    const allowed: ChatContextSourceType[] = [
      'knowledge_library',
      'uploaded_file',
      'mcp_connector',
      ...STRUCTURED_TYPES,
    ]
    return parsed.filter(item => allowed.includes(item?.type) && item.id && item.name)
  } catch {
    return null
  }
}

export function contextSourcesEqual(a: ChatContextSource[], b: ChatContextSource[]): boolean {
  if (a.length !== b.length) return false
  return a.every((item, idx) => item.type === b[idx]?.type && item.id === b[idx]?.id)
}

export function knowledgeLibraryIds(sources: ChatContextSource[]): string[] {
  return sources.filter(s => s.type === 'knowledge_library').map(s => s.id)
}

export function uploadedFileIds(sources: ChatContextSource[]): string[] {
  return sources.filter(s => s.type === 'uploaded_file').map(s => s.id)
}

export function validateContextMix(sources: ChatContextSource[]): string | null {
  const hasLib = sources.some(s => s.type === 'knowledge_library')
  const hasFile = sources.some(s => s.type === 'uploaded_file')
  const hasStructured = sources.some(s => STRUCTURED_TYPES.includes(s.type))
  const hasMcp = sources.some(s => s.type === 'mcp_connector')
  const families = [hasLib, hasFile, hasStructured, hasMcp].filter(Boolean).length
  if (families > 1) {
    return 'Use one context family per request: Knowledge, uploaded files, MCP, or structured data (@ table/metric/semantic).'
  }
  if (hasLib && hasFile) {
    return 'This version supports either Knowledge context or uploaded document context in a single request.'
  }
  return null
}

export function mergeKnowledgeLibraryContext(
  current: ChatContextSource[],
  next: ChatContextSource,
  { allowMultiple = true }: { allowMultiple?: boolean } = {},
): ChatContextSource[] {
  const withoutKnowledge = current.filter(s => s.type !== 'knowledge_library' || s.id !== next.id)
  const withoutFiles = withoutKnowledge.filter(s => s.type !== 'uploaded_file')
  const withoutStructured = withoutFiles.filter(s => !STRUCTURED_TYPES.includes(s.type))
  const withoutMcp = withoutStructured.filter(s => s.type !== 'mcp_connector')
  if (!allowMultiple) {
    return [next]
  }
  const knowledge = withoutMcp.filter(s => s.type === 'knowledge_library')
  const files = withoutKnowledge.filter(s => s.type === 'uploaded_file')
  const structured = withoutKnowledge.filter(s => STRUCTURED_TYPES.includes(s.type))
  const mcp = withoutKnowledge.filter(s => s.type === 'mcp_connector')
  if (next.type === 'knowledge_library') {
    return [...files, ...structured, ...mcp, ...knowledge.filter(s => s.id !== next.id), next]
  }
  if (next.type === 'mcp_connector') {
    return [...knowledge, ...files, ...structured, ...mcp.filter(s => s.id !== next.id), next]
  }
  if (STRUCTURED_TYPES.includes(next.type)) {
    return [...knowledge, ...files, ...mcp, ...structured.filter(s => s.id !== next.id), next]
  }
  return [...knowledge, ...structured, ...mcp, ...files.filter(s => s.id !== next.id), next]
}

export function removeContextSource(current: ChatContextSource[], id: string): ChatContextSource[] {
  return current.filter(s => s.id !== id)
}
