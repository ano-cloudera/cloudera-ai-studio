import { describe, expect, it } from 'vitest'

import { formatHandlerType, formatPromptKey, formatToolName } from './promptSkillDisplay'

describe('promptSkillDisplay', () => {
  it('formats handler types for display', () => {
    expect(formatHandlerType('ask_data')).toBe('Ask Data')
    expect(formatHandlerType('prompt_only')).toBe('Prompt Only')
    expect(formatHandlerType('rag')).toBe('RAG')
  })

  it('formats tool names for display', () => {
    expect(formatToolName('document_retrieval')).toBe('Document Retrieval')
  })

  it('formats prompt keys without changing internal values', () => {
    expect(formatPromptKey('ask_data.system')).toBe('Ask Data System')
    expect(formatPromptKey('ask_data.system')).not.toBe('ask_data')
  })
})
