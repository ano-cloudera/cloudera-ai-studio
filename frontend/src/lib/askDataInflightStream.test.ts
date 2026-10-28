import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from './api'
import {
  abortInflightStream,
  inflightStreamSessionId,
  startInflightStream,
  subscribeInflightStream,
} from './askDataInflightStream'

vi.mock('./api', () => ({
  api: {
    chatStream: vi.fn(),
  },
}))

async function* delayedDone() {
  await new Promise(r => setTimeout(r, 30))
  yield {
    type: 'done' as const,
    response: {
      request_id: 'req-1',
      status: 'SUCCESS',
      answer: { executive_summary: 'Done.' },
    },
  }
}

describe('askDataInflightStream', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.mocked(api.chatStream).mockImplementation(() => delayedDone())
  })

  afterEach(() => {
    abortInflightStream()
    vi.clearAllMocks()
  })

  it('keeps streaming after subscriber unsubscribes (tab navigation)', async () => {
    const sessionId = 'sess-nav-test'
    const loadingSnapshots: boolean[] = []

    startInflightStream({
      sessionId,
      selection: { provider: 'openai', model: 'gpt-4o-mini' },
      question: 'hello',
      userMessage: { role: 'user', content: 'hello' },
      priorMessages: [],
      streamTimeoutMs: 60_000,
      contextPayload: { mode: 'ask_data' },
    })

    expect(inflightStreamSessionId()).toBe(sessionId)

    const unsubscribe = subscribeInflightStream(s => {
      loadingSnapshots.push(s.loading)
    })
    unsubscribe()

    await vi.waitFor(() => {
      expect(inflightStreamSessionId()).toBeNull()
    })

    expect(loadingSnapshots.some(Boolean)).toBe(true)
    expect(api.chatStream).toHaveBeenCalled()
  })
})
