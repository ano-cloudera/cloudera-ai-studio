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

  it('keeps numbered lines as before', () => {
    render(<AnswerProse text={'1. First\n2. Second'} />)
    expect(screen.getByText('1.')).toBeTruthy()
  })
})
