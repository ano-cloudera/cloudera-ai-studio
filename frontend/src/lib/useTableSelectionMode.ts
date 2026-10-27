import { useCallback, useState } from 'react'

/** Explicit bulk-selection mode (checkbox column hidden until active). */
export function useTableSelectionMode(clearSelection: () => void) {
  const [active, setActive] = useState(false)

  const enter = useCallback(() => setActive(true), [])

  const exit = useCallback(() => {
    setActive(false)
    clearSelection()
  }, [clearSelection])

  return { active, enter, exit }
}
