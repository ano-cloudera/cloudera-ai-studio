import type { ChatResponse } from '../types/api'

export type ClarificationChoice = {
  id: string
  label: string
  /** Short reply merged with prior question on the backend (contextualize_question). */
  submitText: string
  contextSource?: { type: string; id: string; name: string }
}

function combinedAnswerText(response: ChatResponse): string {
  const parts = [
    response.answer.direct_answer,
    response.answer.executive_summary,
    ...(response.answer.insights ?? []),
  ]
  return parts.filter(Boolean).join(' ').toLowerCase().replace(/–/g, '-')
}

/** Quick-reply chips when the assistant asks a known clarification pattern (domain-neutral). */
export function clarificationChoices(response: ChatResponse): ClarificationChoice[] | null {
  if (response.clarification?.options?.length) {
    return response.clarification.options.map(opt => ({
      id: opt.id,
      label: opt.name,
      submitText: opt.name,
      contextSource: { type: opt.type, id: opt.id, name: opt.name },
    }))
  }
  if (
    response.status !== 'CLARIFICATION' &&
    response.status !== 'clarification_required' &&
    response.strategy !== 'clarification'
  ) {
    return null
  }
  const text = combinedAnswerText(response)

  if (text.includes('sell-in') && text.includes('sell-out')) {
    return [
      { id: 'sell-in', label: 'Inbound (supplier → channel)', submitText: 'Use inbound sales (supplier to channel)' },
      { id: 'sell-out', label: 'Outbound (channel → customer)', submitText: 'Use outbound sales (channel to customer)' },
    ]
  }

  if (
    (text.includes('warehouse') && text.includes('store')) ||
    (text.includes('distribution center') && text.includes('retail'))
  ) {
    return [
      { id: 'wh', label: 'Warehouse stock', submitText: 'Warehouse inventory levels' },
      { id: 'dc', label: 'Distribution center stock', submitText: 'Distribution center inventory levels' },
      { id: 'store', label: 'Retail store stock', submitText: 'Retail store inventory levels' },
    ]
  }

  if (text.includes('sell-out') && text.includes('sell-in') && text.includes('ratio')) {
    return [
      { id: 'so_si', label: 'Outbound / Inbound', submitText: 'Ratio of outbound to inbound sales' },
      { id: 'si_so', label: 'Inbound / Outbound', submitText: 'Ratio of inbound to outbound sales' },
    ]
  }

  if (text.includes('fulfillment') && text.includes('billing')) {
    return [
      { id: 'fill', label: 'Order fulfillment rate', submitText: 'Order fulfillment rate by product' },
      { id: 'billing', label: 'Billing amount', submitText: 'Total billing amount by product' },
    ]
  }

  if (text.includes('inventory') && text.includes('sales') && text.includes('compare')) {
    return [
      { id: 'inv', label: 'Inventory value', submitText: 'Inventory value by location' },
      { id: 'sales', label: 'Sales volume', submitText: 'Sales volume by region' },
    ]
  }

  if (text.includes('picking') && text.includes('unloading')) {
    return [
      { id: 'picking', label: 'Picking duration', submitText: 'Average picking duration by site' },
      { id: 'unloading', label: 'Unloading duration', submitText: 'Average unloading duration by site' },
    ]
  }

  return null
}
