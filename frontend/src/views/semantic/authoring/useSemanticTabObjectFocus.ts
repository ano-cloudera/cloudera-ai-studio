import { useEffect, useRef } from 'react'

/** Open the authoring drawer when parent sets focusObjectId (e.g. Overview → View in tab). */
export function useSemanticTabObjectFocus<T extends { id: string }>(
  focusObjectId: string | null | undefined,
  versionId: string | null,
  fetchAll: (versionId: string) => Promise<T[]>,
  openRecord: (row: T) => void,
  onConsumed?: () => void,
) {
  const lastOpenedRef = useRef<string | null>(null)

  useEffect(() => {
    if (!focusObjectId) {
      lastOpenedRef.current = null
    }
  }, [focusObjectId])

  useEffect(() => {
    if (!focusObjectId || !versionId) return
    if (lastOpenedRef.current === focusObjectId) return

    let cancelled = false
    void fetchAll(versionId).then(rows => {
      if (cancelled) return
      const row = rows.find(r => r.id === focusObjectId)
      if (!row) return
      openRecord(row)
      lastOpenedRef.current = focusObjectId
      onConsumed?.()
    })

    return () => {
      cancelled = true
    }
  }, [focusObjectId, versionId, fetchAll, openRecord, onConsumed])
}
