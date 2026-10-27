import { describe, expect, it } from 'vitest'

import {
  formatTimeAxisLabel,
  isTimeAxisField,
  parseTimeAxisMs,
} from './businessPresentation'

describe('time axis labels', () => {
  it('detects banking transaction date columns', () => {
    expect(isTimeAxisField('transactions_transaction_date')).toBe(true)
  })

  it('formats ISO timestamps as short month year', () => {
    const label = formatTimeAxisLabel('2026-08-01T00:00:00.000Z')
    expect(label).toMatch(/2026/)
    expect(label?.length).toBeLessThan(16)
  })

  it('parses ISO for sorting', () => {
    const a = parseTimeAxisMs('2026-06-01T00:00:00Z')
    const b = parseTimeAxisMs('2026-09-01T00:00:00Z')
    expect(a).not.toBeNull()
    expect(b).not.toBeNull()
    expect(a! < b!).toBe(true)
  })
})
