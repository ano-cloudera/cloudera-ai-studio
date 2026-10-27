import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useTableSelectionMode } from './useTableSelectionMode'

describe('useTableSelectionMode', () => {
  it('enters and exits selection mode', () => {
    const clear = vi.fn()
    const { result } = renderHook(() => useTableSelectionMode(clear))
    expect(result.current.active).toBe(false)
    act(() => result.current.enter())
    expect(result.current.active).toBe(true)
    act(() => result.current.exit())
    expect(result.current.active).toBe(false)
    expect(clear).toHaveBeenCalledTimes(1)
  })
})
