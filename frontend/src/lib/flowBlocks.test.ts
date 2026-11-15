import { describe, expect, it } from 'vitest'

import { flowBlock } from './flowBlocks'

describe('flowBlock', () => {
  it('draws three or more numbered steps as a flow', () => {
    expect(flowBlock('1. Catat LO\n2. Eskalasi ke manajer\n3. Buat tiket')).toEqual({ kind: 'steps', items: ['Catat LO', 'Eskalasi ke manajer', 'Buat tiket'] })
  })

  it('keeps a short numbered list as text', () => {
    expect(flowBlock('1. Satu\n2. Dua')).toBeNull()
  })

  it('draws action lines with arrows as hand-overs', () => {
    expect(flowBlock('- Terminal Manager → rencana perbaikan → 3 hari kerja\n- Region Manager → tiket prioritas')).toEqual({
      kind: 'handoffs',
      rows: [['Terminal Manager', 'rencana perbaikan', '3 hari kerja'], ['Region Manager', 'tiket prioritas']],
    })
  })

  it('leaves plain bullets and prose alone', () => {
    expect(flowBlock('- satu\n- dua')).toBeNull()
    expect(flowBlock('Sebuah kalimat.\n1. campur')).toBeNull()
  })
})
