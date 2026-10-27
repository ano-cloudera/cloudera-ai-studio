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
