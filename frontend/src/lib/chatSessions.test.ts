import { beforeEach, describe, expect, it } from 'vitest'

import { loadSessions, renameSession, saveSession, toggleSessionPinned } from './chatSessions'

describe('chat session persistence', () => {
  beforeEach(() => localStorage.clear())

  it('persists the provider and model with the conversation', () => {
    saveSession({
      id: 'session-1', title: 'Question', updatedAt: 1,
      messages: [{ role: 'user', content: 'Question' }],
      selection: { provider: 'gemini', model: 'gemini-configured' },
    })

    expect(loadSessions()[0].selection).toEqual({ provider: 'gemini', model: 'gemini-configured' })
  })

  it('keeps pinned sessions above recent ones', () => {
    saveSession({
      id: 'old', title: 'Old', updatedAt: 1,
      messages: [{ role: 'user', content: 'Old' }],
    })
    saveSession({
      id: 'new', title: 'New', updatedAt: 99,
      messages: [{ role: 'user', content: 'New' }],
    })
    toggleSessionPinned('old')
    const sessions = loadSessions()
    expect(sessions[0].id).toBe('old')
    expect(sessions[0].pinned).toBe(true)
    expect(sessions[1].id).toBe('new')
  })

  it('renames a session and keeps the custom title on auto-save', () => {
    saveSession({
      id: 's1',
      title: 'hallo kamu bisa bantu apa ?',
      updatedAt: 1,
      messages: [{ role: 'user', content: 'hallo kamu bisa bantu apa ?' }],
    })
    renameSession('s1', 'Q4 Pareto review')
    saveSession({
      id: 's1',
      title: 'hallo kamu bisa bantu apa ?',
      updatedAt: 2,
      messages: [
        { role: 'user', content: 'hallo kamu bisa bantu apa ?' },
        { role: 'user', content: 'tampilkan pareto' },
      ],
    })
    expect(loadSessions()[0].title).toBe('Q4 Pareto review')
    expect(loadSessions()[0].titleCustomized).toBe(true)
  })
})
