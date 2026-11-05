import type { ChatResponse } from '../types/api'

export type ClarificationChoice = {
  id: string
  label: string
  /** The reply sent when the chip is picked. */
  submitText: string
  contextSource?: { type: string; id: string; name: string }
}

/** Quick-reply chips for the options the backend offered with a clarification. */
export function clarificationChoices(response: ChatResponse): ClarificationChoice[] | null {
  if (response.clarification?.options?.length) {
    return response.clarification.options.map(opt => ({
      id: opt.id,
      label: opt.name,
      submitText: opt.name,
      contextSource: { type: opt.type, id: opt.id, name: opt.name },
    }))
  }
  return null
}
