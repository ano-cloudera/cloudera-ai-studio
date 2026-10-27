import type { ChatResponse } from '../types/api'
import { getPresentationTierConfig } from './presentationTierConfig'

export type AudienceMode = 'executive' | 'analyst'

export function getAudienceMode(): AudienceMode {
  const mode = getPresentationTierConfig().audience_mode
  return mode === 'analyst' ? 'analyst' : 'executive'
}

export function isExecutiveAudience(): boolean {
  return getAudienceMode() === 'executive'
}

const TECHNICAL_NOTE =
  /\b(select|sum\s*\(|count\s*\(|group by|where\s+|from\s+\w+\.\w+|execution_ms|query_id|governed queries)\b/i

export function isTechnicalDataNote(text: string): boolean {
  return TECHNICAL_NOTE.test(text)
}

/** Business-facing metric label (avoid internal semantic keys in UI). */
export function metricDisplayLabel(response: ChatResponse): string | null {
  const title = response.chart_spec?.title?.trim()
  if (title && !title.match(/^[a-z0-9_]+$/i)) return title
  const governed = response.data.governed_metric?.trim()
  if (governed) {
    return governed
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase())
      .replace(/\s+/g, ' ')
      .trim()
  }
  return title || null
}

export function executiveTrustLine(response: ChatResponse): string | null {
  if (response.context_mode !== 'GOVERNED_SEMANTIC') return null
  const label = metricDisplayLabel(response)
  if (label) return `Angka terverifikasi · ${label}`
  return 'Angka terverifikasi · semantic model'
}

export function executiveSourceHint(sources: string[]): string | null {
  if (!sources.length) return null
  const first = sources[0]
  if (!first) return null
  const schema = first.split('.')[0]
  if (schema && schema !== first) {
    return `Sumber data: ${schema.replace(/_/g, ' ')}`
  }
  return null
}

export function noteForExecutive(note: string | null, sources: string[]): string | null {
  const hint = executiveSourceHint(sources)
  if (!note || isTechnicalDataNote(note)) return hint
  if (note.length > 180 || isTechnicalDataNote(note)) return hint
  return note
}
