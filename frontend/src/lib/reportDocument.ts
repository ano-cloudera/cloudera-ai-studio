import type { ChatResponse } from '../types/api'
import { computePresentationTier, shouldAutoOpenAnalysisPanel } from './presentationTier'

export type ReportSection = {
  id: string
  userQuestion: string
  response: ChatResponse
}

export function reportSectionTitle(response: ChatResponse): string {
  const chartTitle = response.chart_spec?.title?.trim()
  if (chartTitle) return chartTitle
  const direct = response.answer.direct_answer.trim()
  if (direct.length <= 80) return direct
  return `${direct.slice(0, 77)}…`
}

export function reportSectionsFromMessages(
  messages: { role: string; content: string; response?: ChatResponse }[],
  options?: { pinnedRequestIds?: string[] },
): ReportSection[] {
  const pinned = new Set(options?.pinnedRequestIds ?? [])
  const sections: ReportSection[] = []
  let lastUser = ''
  for (let i = 0; i < messages.length; i += 1) {
    const message = messages[i]
    if (message.role === 'user') {
      lastUser = message.content
      continue
    }
    if (message.role !== 'assistant' || !message.response) continue
    if (message.response.status !== 'SUCCESS') continue
    if (!responseHasReportEvidence(message.response)) continue
    const id = message.response.request_id || `turn-${i}`
    const tier = computePresentationTier(message.response)
    if (tier !== 3 && !pinned.has(id)) continue
    sections.push({
      id,
      userQuestion: lastUser,
      response: message.response,
    })
  }
  return sections
}

export function canOpenAnalysisWorkspace(response: ChatResponse): boolean {
  return response.status === 'SUCCESS' && responseHasReportEvidence(response)
}

export function responseHasReportEvidence(response: ChatResponse): boolean {
  const visual = ['bar', 'line', 'area', 'scatter', 'pie']
  const hasChart =
    Boolean(response.chart_spec?.type) &&
    (response.chart_spec?.type === 'kpi' ||
      (visual.includes(response.chart_spec?.type ?? '') &&
        response.chart_spec?.x &&
        response.chart_spec?.y &&
        response.data.rows.length > 0))
  return hasChart || response.data.rows.length > 0
}

export function responseQualifiesForReportPanel(response: ChatResponse): boolean {
  return shouldAutoOpenAnalysisPanel(response)
}
