import type { ChatResponse } from '../types/api'
import type { ModelSelection } from '../types/api'
import type { ProgressTraceEntry } from './streamProgress'

export type ProcessSnapshot = {
  activeStepIndex: number
  technicalTrace: ProgressTraceEntry[]
}

export type StoredMessage = {
  role: 'user' | 'assistant'
  content: string
  /** The question that was sent, when the bubble shows something shorter (a picked metric). */
  asked?: string
  response?: ChatResponse
  processSnapshot?: ProcessSnapshot
}
export type ChatSession = {
  id: string
  title: string
  updatedAt: number
  messages: StoredMessage[]
  selection?: ModelSelection
  pinned?: boolean
  /** When true, title is kept on save (not replaced by first user message). */
  titleCustomized?: boolean
}

const STORAGE_KEY = 'ai-studio.ask-data.sessions'
const CURRENT_KEY = 'ai-studio.ask-data.current-session'

/** The session open in this browser tab, so coming back to Ask Data from another page continues it under the same id. */
export function readCurrentSessionId(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage.getItem(CURRENT_KEY)
  } catch {
    return null
  }
}

export function writeCurrentSessionId(id: string): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(CURRENT_KEY, id)
  } catch {
    // storage unavailable: a visit to another page starts a new chat, nothing worse
  }
}
const MAX_SESSIONS = 20

export function createSessionId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function loadSessions(): ChatSession[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return sortSessionsForDisplay(Array.isArray(parsed) ? parsed : [])
  } catch {
    return []
  }
}

export function sortSessionsForDisplay(sessions: ChatSession[]): ChatSession[] {
  return [...sessions].sort((a, b) => {
    const pinDelta = Number(Boolean(b.pinned)) - Number(Boolean(a.pinned))
    if (pinDelta !== 0) return pinDelta
    return b.updatedAt - a.updatedAt
  })
}

function writeSessions(sessions: ChatSession[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, MAX_SESSIONS)))
}

export function saveSession(session: ChatSession) {
  if (typeof window === 'undefined' || !session.messages.length) return
  try {
    const prior = loadSessions()
    const existing = prior.find(item => item.id === session.id)
    const merged: ChatSession = {
      ...session,
      title: existing?.titleCustomized ? existing.title : session.title,
      titleCustomized: existing?.titleCustomized ?? session.titleCustomized,
      pinned: session.pinned ?? existing?.pinned,
    }
    const sessions = sortSessionsForDisplay([
      merged,
      ...prior.filter(item => item.id !== session.id),
    ])
    writeSessions(sessions)
  } catch {
    // localStorage unavailable (private mode, quota) - session just won't persist across reloads.
  }
}

export function deleteSession(id: string) {
  if (typeof window === 'undefined') return
  try {
    writeSessions(loadSessions().filter(item => item.id !== id))
  } catch {
    // localStorage unavailable - nothing to clean up.
  }
}

const MAX_TITLE_LENGTH = 80

export function renameSession(id: string, title: string): ChatSession[] {
  if (typeof window === 'undefined') return []
  const trimmed = title.trim()
  if (!trimmed) return loadSessions()
  try {
    const nextTitle = trimmed.slice(0, MAX_TITLE_LENGTH)
    const sessions = sortSessionsForDisplay(
      loadSessions().map(item =>
        item.id === id ? { ...item, title: nextTitle, titleCustomized: true } : item,
      ),
    )
    writeSessions(sessions)
    return sessions
  } catch {
    return loadSessions()
  }
}

export function toggleSessionPinned(id: string): ChatSession[] {
  if (typeof window === 'undefined') return []
  try {
    const sessions = sortSessionsForDisplay(
      loadSessions().map(item => (item.id === id ? { ...item, pinned: !item.pinned } : item)),
    )
    writeSessions(sessions)
    return sessions
  } catch {
    return loadSessions()
  }
}

export function sessionTitle(messages: StoredMessage[]): string {
  return messages.find(message => message.role === 'user')?.content.slice(0, 80) || 'New conversation'
}
