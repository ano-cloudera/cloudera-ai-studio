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

  it('selects and clears an entire dataset from the header', () => {
    const { result } = renderHook(() => useTableSelection())
    expect(result.current.datasetCheckboxState(3)).toBe('unchecked')
    act(() => result.current.toggleDatasetSelection(['a', 'b', 'c'], 3))
    expect(result.current.selectedCount).toBe(3)
    expect(result.current.datasetCheckboxState(3)).toBe('checked')
    act(() => result.current.toggleDatasetSelection(['a', 'b', 'c'], 3))
    expect(result.current.selectedCount).toBe(0)
  })
})
