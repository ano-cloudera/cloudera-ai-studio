import type { ChatResponse, CitationRecord } from '../types/api'

export function isRagResponse(response: ChatResponse): boolean {
  return response.strategy === 'rag' || response.route === 'rag'
}

export function ragCitationCount(response: ChatResponse): number {
  return response.citations?.length ?? 0
}

export function responseHasRagWorkspace(response: ChatResponse): boolean {
  if (!isRagResponse(response)) return false
  if (response.status === 'SUCCESS' || response.status === 'NO_DATA') return true
  return false
}

export function formatCitationLabel(cite: CitationRecord, index: number): string {
  const name = cite.filename?.trim() || `Document ${index + 1}`
  const page = cite.page_number != null ? ` · Page ${cite.page_number}` : ''
  const section = cite.section?.trim() ? ` · ${cite.section}` : ''
  return `${name}${page}${section}`
}

/** Chunks are cut by length, so a snippet can start inside a word; drop that fragment and mark the cut. */
export function tidySnippet(raw: string | null | undefined): string {
  const text = (raw ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  if (/^[a-z]/.test(text)) {
    const firstSpace = text.indexOf(' ')
    if (firstSpace > 0) return `\u2026${text.slice(firstSpace + 1)}`
  }
  return text
}

/** Link to the stored original, opened at the cited page; only PDFs can be previewed in the browser. */
export function citationPdfUrl(cite: CitationRecord): string | null {
  if (!cite.document_id || !/\.pdf$/i.test(cite.filename ?? '')) return null
  const page = cite.page_number != null && cite.page_number > 0 ? `#page=${cite.page_number}` : ''
  return `/api/v1/documents/${encodeURIComponent(cite.document_id)}/file${page}`
}
