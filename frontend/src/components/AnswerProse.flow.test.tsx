import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { AnswerProse } from './AnswerProse'

describe('AnswerProse flow and table', () => {
  afterEach(cleanup)

  it('draws numbered steps and hand-overs as diagrams', () => {
    render(<AnswerProse text={'### Langkah Penanganan\n\n1. Catat LO\n2. Eskalasi\n3. Buat tiket\n\n### Tindak Lanjut\n\n- Manajer → buat tiket → 24 jam'} />)
    expect(screen.getAllByTestId('flow-diagram')).toHaveLength(2)
    expect(screen.getByText('Eskalasi')).toBeTruthy()
  })

  it('gives a table the violet header the other tables have', () => {
    const { container } = render(<AnswerProse text={'| A | B |\n| --- | --- |\n| 1 | 2 |'} />)
    expect(container.querySelector('thead.app-table-head')).not.toBeNull()
  })
})
