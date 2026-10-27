import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useTableSelection } from './useTableSelection'

describe('useTableSelection', () => {
  it('tracks IDs across toggles and page select', () => {
    const { result } = renderHook(() => useTableSelection())
    act(() => result.current.toggle('a'))
    act(() => result.current.toggle('c'))
    expect(result.current.selectedCount).toBe(2)
    expect(result.current.pageCheckboxState(['a', 'b', 'c'])).toBe('indeterminate')
    act(() => result.current.togglePage(['a', 'b']))
    expect(result.current.pageCheckboxState(['a', 'b'])).toBe('checked')
    act(() => result.current.togglePage(['a', 'b']))
    expect(result.current.isSelected('a')).toBe(false)
    expect(result.current.isSelected('c')).toBe(true)
  })
})
