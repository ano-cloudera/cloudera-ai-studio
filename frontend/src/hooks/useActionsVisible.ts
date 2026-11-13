'use client'

import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const KEY = 'ai-studio.actions-visible'

function remembered(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/** Whether the Actions page has anything to show. The last answer is used at once so the menu does not jump; the Backend's
 * answer replaces it (an enabled MCP server offers an action tool, or an action was run). Any failure leaves the menu without it. */
export function useActionsVisible(): boolean {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    setVisible(remembered())
    let alive = true
    Promise.resolve()
      .then(() => api.mcpActionStatus())
      .then(status => {
        if (!alive) return
        setVisible(status.visible)
        try {
          window.sessionStorage.setItem(KEY, status.visible ? '1' : '0')
        } catch {
          // the menu is right for this visit anyway
        }
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  return visible
}
