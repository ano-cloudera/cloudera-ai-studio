import type { ChatResponse } from '../types/api'

const NO_GOVERNED = /no governed query result attached/i
const GOVERNED_QUERY = /governed queries:/i
const QUERY_ID = /\b[A-Z]{2}-\d{2}@[a-z0-9_]+/i
const GOLD_VIEW = /\bgold\.[a-z0-9_]+/i

export function hasGovernedEvidence(response: ChatResponse): boolean {
  if (response.strategy === 'conversational') return true
  if ((response.data?.row_count ?? 0) > 0) return true
  const ref = response.answer?.data_reference ?? ''
  if (!ref || NO_GOVERNED.test(ref)) return false
  return GOVERNED_QUERY.test(ref) || QUERY_ID.test(ref) || GOLD_VIEW.test(ref)
}

export function displayStatus(response: ChatResponse): ChatResponse['status'] {
  if (
    response.status === 'SUCCESS'
    && response.strategy === 'governed'
    && !hasGovernedEvidence(response)
  ) {
    return 'NO_DATA'
  }
  if (response.status === 'ERROR' && hasGovernedEvidence(response)) {
    return 'SUCCESS'
  }
  return response.status
}

/** Headline + optional status chip — avoids alarming ERROR copy when data is still useful. */
export function answerPresentation(response: ChatResponse): {
  title: string
  showStatusChip: boolean
  statusChip: ChatResponse['status'] | null
} {
  const uiStatus = displayStatus(response)
  const conversational = response.strategy === 'conversational'

  if (uiStatus === 'SUCCESS') {
    return {
      title: conversational ? 'Welcome' : 'Direct answer',
      showStatusChip: false,
      statusChip: null,
    }
  }
  if (uiStatus === 'CLARIFICATION') {
    return {
      title: 'A quick clarification',
      showStatusChip: true,
      statusChip: 'CLARIFICATION',
    }
  }
  if (uiStatus === 'NO_DATA') {
    return {
      title: 'No matching data',
      showStatusChip: true,
      statusChip: 'NO_DATA',
    }
  }
  if (uiStatus === 'UNSUPPORTED') {
    return {
      title: 'Outside the current scope',
      showStatusChip: true,
      statusChip: 'UNSUPPORTED',
    }
  }
  return {
    title: 'Direct answer',
    showStatusChip: false,
    statusChip: null,
  }
}
