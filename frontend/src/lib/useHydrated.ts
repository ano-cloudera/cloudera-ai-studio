'use client'

import { useEffect, useState } from 'react'

/** True after the client has mounted — use to avoid SSR/client mismatches (localStorage, etc.). */
export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false)
  useEffect(() => setHydrated(true), [])
  return hydrated
}
