import { describe, expect, it } from 'vitest'

import { nextSortState } from './tableSort'

describe('nextSortState', () => {
  it('starts new column at DESC', () => {
    expect(nextSortState('updated_at', 'desc', 'name')).toEqual({ field: 'name', order: 'desc' })
  })

  it('toggles order on same column', () => {
    expect(nextSortState('updated_at', 'desc', 'updated_at')).toEqual({ field: 'updated_at', order: 'asc' })
    expect(nextSortState('updated_at', 'asc', 'updated_at')).toEqual({ field: 'updated_at', order: 'desc' })
  })
})
