import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './api'


function sseResponse(chunks: string[]) {
  const encoder = new TextEncoder()
  let index = 0
  const body = {
    getReader: () => ({
      read: async () => {
        if (index >= chunks.length) return { done: true, value: undefined }
        const value = encoder.encode(chunks[index++])
        return { done: index >= chunks.length, value }
      },
    }),
  }
  return { ok: true, body } as unknown as Response
}


describe('V2 API client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends only the selected backend-discovered provider and model', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([
      `data: ${JSON.stringify({ type: 'done', response: { status: 'SUCCESS' } })}\n\n`,
    ]))
    vi.stubGlobal('fetch', fetchMock)

    const events = []
    for await (const event of api.chatStream('question', 'session-1', { provider: 'gemini', model: 'gemini-configured' })) events.push(event)

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      question: 'question', session_id: 'session-1', provider: 'gemini', model: 'gemini-configured',
    })
    expect(events.at(-1)).toEqual({ type: 'done', response: { status: 'SUCCESS' } })
  })

  it('passes an abort signal to the streaming request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([
      `data: ${JSON.stringify({ type: 'done', response: { status: 'SUCCESS' } })}\n\n`,
    ]))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    for await (const _ of api.chatStream('q', 's', { provider: 'qwen', model: 'qwen' }, controller.signal)) { /* consume */ }

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('drains a final done frame delivered with done=true', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
      `data: ${JSON.stringify({ type: 'progress', stage: 'querying_data', label: 'Querying data' })}\n\ndata: ${JSON.stringify({ type: 'done', response: { status: 'SUCCESS' } })}\n\n`,
    ])))

    const events = []
    for await (const event of api.chatStream('q', 's', { provider: 'qwen', model: 'qwen' })) events.push(event)

    expect(events.map(event => event.type)).toEqual(['progress', 'done'])
  })

  it('rejects a stream that closes without a terminal frame', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
      `data: ${JSON.stringify({ type: 'progress', stage: 'querying_data', label: 'Querying data' })}\n\n`,
    ])))

    const consume = async () => {
      for await (const _ of api.chatStream('q', 's', { provider: 'qwen', model: 'qwen' })) { /* consume */ }
    }
    await expect(consume()).rejects.toThrow('Stream ended without a terminal response')
  })
})
