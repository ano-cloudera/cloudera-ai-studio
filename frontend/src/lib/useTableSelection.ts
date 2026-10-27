import { useCallback, useMemo, useState } from 'react'

export type PageCheckboxState = 'unchecked' | 'checked' | 'indeterminate'

export function useTableSelection() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())

  const selectedCount = selectedIds.size

  const isSelected = useCallback((id: string) => selectedIds.has(id), [selectedIds])

  const toggle = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const clear = useCallback(() => setSelectedIds(new Set()), [])

  const setSelection = useCallback((ids: Iterable<string>) => {
    setSelectedIds(new Set(ids))
  }, [])

  const pageCheckboxState = useCallback(
    (visibleIds: string[]): PageCheckboxState => {
      if (!visibleIds.length) return 'unchecked'
      const selectedOnPage = visibleIds.filter(id => selectedIds.has(id)).length
      if (selectedOnPage === 0) return 'unchecked'
      if (selectedOnPage === visibleIds.length) return 'checked'
      return 'indeterminate'
    },
    [selectedIds],
  )

  const togglePage = useCallback((visibleIds: string[]) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      const allSelected = visibleIds.length > 0 && visibleIds.every(id => next.has(id))
      if (allSelected) {
        visibleIds.forEach(id => next.delete(id))
      } else {
        visibleIds.forEach(id => next.add(id))
      }
      return next
    })
  }, [])

  const selectedList = useMemo(() => [...selectedIds], [selectedIds])

  return {
    selectedIds,
    selectedCount,
    selectedList,
    isSelected,
    toggle,
    clear,
    setSelection,
    pageCheckboxState,
    togglePage,
  }
}
