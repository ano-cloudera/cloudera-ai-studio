import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

import { usePlatformReadiness } from './usePlatformReadiness'

describe('usePlatformReadiness', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fresh clean env: core_ready with empty feature_gaps → ready', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          core_ready: true,
          status: 'ready',
          feature_gaps: [],
        }),
      }),
    )
    const { result } = renderHook(() => usePlatformReadiness(999_999))
    await waitFor(() => expect(result.current.status).toBe('ready'))
  })

  it('unconfigured ask data notice must not degrade when status is ready', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          core_ready: true,
          status: 'ready',
          feature_gaps: [],
          components: { llm: 'not_configured', legacy_datasource: 'not_configured' },
        }),
      }),
    )
    const { result } = renderHook(() => usePlatformReadiness(999_999))
    await waitFor(() => expect(result.current.status).toBe('ready'))
  })

  it('core_ready false → unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ core_ready: false, status: 'not_ready', feature_gaps: [] }),
      }),
    )
    const { result } = renderHook(() => usePlatformReadiness(999_999))
    await waitFor(() => expect(result.current.status).toBe('unavailable'))
  })

  it('optional service failure → degraded', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          core_ready: true,
          status: 'not_ready',
          feature_gaps: ['rag_needs_qdrant'],
        }),
      }),
    )
    const { result } = renderHook(() => usePlatformReadiness(999_999))
    await waitFor(() => expect(result.current.status).toBe('degraded'))
  })

  it('HTTP not ok → unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    const { result } = renderHook(() => usePlatformReadiness(999_999))
    await waitFor(() => expect(result.current.status).toBe('unavailable'))
  })
})
