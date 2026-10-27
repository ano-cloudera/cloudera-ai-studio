/** User-facing labels for prompt/skill identifiers (backend values unchanged). */

const HANDLER_LABELS: Record<string, string> = {
  ask_data: 'Ask Data',
  prompt_only: 'Prompt Only',
  rag: 'RAG',
  document_qa: 'Document Q&A',
}

const TOOL_LABELS: Record<string, string> = {
  document_retrieval: 'Document Retrieval',
  document_qa: 'Document Q&A',
  sql_query: 'SQL Query',
  semantic_query: 'Semantic Query',
}

export function formatHandlerType(value: string | null | undefined): string {
  if (!value) return '—'
  const key = value.trim().toLowerCase()
  if (HANDLER_LABELS[key]) return HANDLER_LABELS[key]
  return titleCaseSnake(key)
}

export function formatToolName(value: string | null | undefined): string {
  if (!value) return '—'
  const key = value.trim().toLowerCase()
  if (TOOL_LABELS[key]) return TOOL_LABELS[key]
  return titleCaseSnake(key)
}

export function formatPromptKey(key: string | null | undefined): string {
  if (!key) return 'None'
  const known: Record<string, string> = {
    'ask_data.system': 'Ask Data System',
    'rag.system': 'RAG System',
    'rag.insufficient_evidence': 'RAG Insufficient Evidence',
  }
  if (known[key]) return known[key]
  return key
    .split('.')
    .map(part => titleCaseSnake(part))
    .join(' · ')
}

export function formatScope(scope: string | null | undefined): string {
  if (!scope) return '—'
  if (scope === 'global') return 'Global'
  if (scope === 'workspace') return 'Workspace'
  if (scope === 'project') return 'Project'
  return titleCaseSnake(scope)
}

export function formatPromptVersionStatus(
  versions: Array<{ status: string; version_number: number }> | undefined,
): { label: string; version: number | null } {
  if (!versions?.length) return { label: '—', version: null }
  const active = versions.find(v => v.status === 'ACTIVE')
  const draft = versions.find(v => v.status === 'DRAFT')
  if (active) return { label: 'Published', version: active.version_number }
  if (draft) return { label: 'Draft', version: draft.version_number }
  const latest = [...versions].sort((a, b) => b.version_number - a.version_number)[0]
  return { label: latest.status === 'ARCHIVED' ? 'Archived' : latest.status, version: latest.version_number }
}

export function formatSkillListStatus(status: string | null | undefined): string {
  if (!status) return '—'
  const s = status.toUpperCase()
  if (s === 'ACTIVE' || s === 'READY' || s === 'PUBLISHED') return 'Published'
  if (s === 'DRAFT') return 'Draft'
  return titleCaseSnake(status)
}

export function formatModified(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  if (sameDay) return 'Today'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function titleCaseSnake(value: string): string {
  return value
    .split(/[._-]+/)
    .filter(Boolean)
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export function slugRegistryKey(name: string, fallbackPrefix: string): string {
  const base =
    name
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '_')
      .replace(/[^a-z0-9_.]/g, '')
      .slice(0, 48) || fallbackPrefix
  return base
}
