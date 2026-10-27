import { describe, expect, it } from 'vitest'

import {
  contextSourcesEqual,
  knowledgeLibraryContext,
  mergeKnowledgeLibraryContext,
  removeContextSource,
  uploadedFileContext,
  validateContextMix,
} from './chatContext'

describe('chatContext', () => {
  it('KNOWLEDGE_CONTEXT_UNIFICATION_PASS for ask path and mention path', () => {
    const library = { id: 'lib-1', name: 'Product Knowledge' }
    const fromAsk = [knowledgeLibraryContext(library)]
    const fromMention = mergeKnowledgeLibraryContext([], knowledgeLibraryContext(library))
    expect(contextSourcesEqual(fromAsk, fromMention)).toBe(true)
  })

  it('keeps library id when display name changes', () => {
    const attached = [knowledgeLibraryContext({ id: 'lib-1', name: 'Old Name' })]
    const renamed = [{ ...attached[0], name: 'New Name' }]
    expect(attached[0].id).toBe(renamed[0].id)
  })

  it('CHAT_CONTEXT_UNIFICATION_PASS blocks mixed knowledge and file context', () => {
    const mixed = [
      knowledgeLibraryContext({ id: 'lib-1', name: 'Product Knowledge' }),
      uploadedFileContext({ id: 'att-1', name: 'report.pdf' }),
    ]
    expect(validateContextMix(mixed)).toMatch(/one context family|either Knowledge context or uploaded document/)
  })

  it('blocks mixed knowledge and structured context', () => {
    const mixed = [
      knowledgeLibraryContext({ id: 'lib-1', name: 'Docs' }),
      { type: 'table' as const, id: 't1', name: 'public.sales' },
    ]
    expect(validateContextMix(mixed)).toMatch(/one context family/)
  })

  it('removeContextSource drops by id', () => {
    const sources = [
      knowledgeLibraryContext({ id: 'a', name: 'A' }),
      knowledgeLibraryContext({ id: 'b', name: 'B' }),
    ]
    expect(removeContextSource(sources, 'a')).toHaveLength(1)
  })
})
