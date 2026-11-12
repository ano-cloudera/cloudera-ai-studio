import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { AnswerProse } from './AnswerProse'

describe('AnswerProse', () => {
  afterEach(cleanup)

  it('renders bullets and bold text without interpreting HTML', () => {
    const { container } = render(
      <AnswerProse text={'Headline **Low** likelihood.\n\n- Score is **below** 650\n- DTI is within the limit\n\n<b>x</b>'} />,
    )
    expect(container.querySelectorAll('strong')).toHaveLength(2)
    expect(screen.getByText('below').tagName).toBe('STRONG')
    expect(container.querySelectorAll('[aria-hidden]').length).toBe(2) // one dot per bullet
    expect(screen.getByText('<b>x</b>')).toBeTruthy() // shown literally, never parsed
  })

  it('lays out a written report: sub-headings, numbered steps and a small table', () => {
    const { container } = render(
      <AnswerProse text={'### Temuan\nPapua Maluku **34,5%**.\n\n| Regional | Late rate |\n|---|---|\n| Papua Maluku | 34,5% |\n| Kalimantan | 29,7% |\n\n1. Audit armada'} />,
    )
    expect(screen.getByText('Temuan').tagName).toBe('H4')
    expect(container.querySelectorAll('tbody tr')).toHaveLength(2)
    expect(screen.getByText('Kalimantan').tagName).toBe('TD')
    expect(screen.getByText('1.')).toBeTruthy()
  })

  it('leaves a table out when the same rows are in the data grid', () => {
    const { container } = render(<AnswerProse omitTables text={'Top.\n\n| a | b |\n|---|---|\n| 1 | 2 |'} />)
    expect(container.querySelector('table')).toBeNull()
    expect(screen.getByText('Top.')).toBeTruthy()
  })

  it('keeps numbered lines as before', () => {
    render(<AnswerProse text={'1. First\n2. Second'} />)
    expect(screen.getByText('1.')).toBeTruthy()
  })
})
