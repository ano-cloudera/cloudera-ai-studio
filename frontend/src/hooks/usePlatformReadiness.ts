'use client'

import { useCallback, useEffect, useState } from 'react'

export type PlatformStatus = 'ready' | 'degraded' | 'unavailable' | 'checking'

export function usePlatformReadiness(pollMs = 60_000): { status: PlatformStatus; refresh: () => void } {
  const [status, setStatus] = useState<PlatformStatus>('checking')

  const refresh = useCallback(() => {
    setStatus('checking')
    fetch('/api/health/ready')
      .then(async res => {
        if (!res.ok) {
          setStatus('unavailable')
          return
        }
        const body = (await res.json()) as { core_ready?: boolean; feature_gaps?: string[] }
        if (body.core_ready === false) {
          setStatus('unavailable')
        } else if (body.feature_gaps?.length) {
          setStatus('degraded')
        } else {
          setStatus('ready')
        }
      })
      .catch(() => setStatus('unavailable'))
  }, [])

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(id)
  }, [refresh, pollMs])

  return { status, refresh }
}
