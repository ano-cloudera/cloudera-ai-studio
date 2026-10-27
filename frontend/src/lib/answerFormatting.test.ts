import { describe, expect, it } from 'vitest'
import { stripMarkdownTables, truncateAxisLabel } from './answerFormatting'

describe('answerFormatting', () => {
  it('removes pipe tables', () => {
    const text = 'Intro\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nOutro'
    expect(stripMarkdownTables(text)).toContain('Intro')
    expect(stripMarkdownTables(text)).toContain('Outro')
    expect(stripMarkdownTables(text)).not.toContain('|')
  })

  it('truncates long axis labels', () => {
    expect(truncateAxisLabel('JKT - DC PURWAKARTA', 12)).toBe('JKT - DC PU…')
  })
})
