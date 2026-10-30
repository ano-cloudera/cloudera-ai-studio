import { describe, expect, it } from 'vitest'
import { sourceHintMessage, suggestSourceHint } from './sourceHint'

describe('suggestSourceHint', () => {
  it('suggests the model tool for an applicant assessment with numbers', () => {
    expect(
      suggestSourceHint('Assess an applicant with credit score 640, DTI 0.40, requested 150 million.', false),
    ).toBe('mcp')
  })

  it('suggests documents for policy-style questions', () => {
    expect(suggestSourceHint('When does an approval-rate gap trigger an investigation?', false)).toBe('knowledge')
    expect(suggestSourceHint('What are the standard approval criteria?', false)).toBe('knowledge')
  })

  it('leaves Ask Data questions alone', () => {
    expect(suggestSourceHint('How many applications were approved by policy exception?', false)).toBeNull()
    expect(suggestSourceHint('What is the approval rate by customer segment?', false)).toBeNull()
    expect(suggestSourceHint('Average credit score by region', false)).toBeNull()
  })

  it('stays quiet once a source is attached or the text is short', () => {
    expect(suggestSourceHint('When does an approval-rate gap trigger an investigation?', true)).toBeNull()
    expect(suggestSourceHint('hello', false)).toBeNull()
  })

  it('words the tip for each source', () => {
    expect(sourceHintMessage('mcp')).toMatch(/credit risk model/)
    expect(sourceHintMessage('knowledge')).toMatch(/knowledge library/)
  })
})
