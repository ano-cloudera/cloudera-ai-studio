import React from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { downloadConversationPdf } from '../lib/chatPdfExport'
import { AppShell } from '../layout/AppShell'
import { appConfig } from '../config/appConfig'
import { renderWithProviders } from '../test/renderWithProviders'
import { AskDataPage } from './AskDataPage'

vi.mock('../lib/api', () => ({
  api: {
    models: vi.fn(),
    randomQueries: vi.fn(),
    chatStream: vi.fn(),
    listLibrariesPaginated: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 100, total: 0, total_pages: 0 }),
    listChatContextOptions: vi.fn().mockResolvedValue({ groups: [] }),
    getLibrary: vi.fn(),
    getChatAttachment: vi.fn(),
    batchUploadChatAttachments: vi.fn(),
    retryChatAttachment: vi.fn(),
    saveChatAttachmentToKnowledge: vi.fn(),
  },
}))
vi.mock('../lib/chatPdfExport', () => ({ downloadConversationPdf: vi.fn().mockResolvedValue(undefined) }))
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}))

describe('V2 Ask Data page', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
    cleanup()
  })

  beforeEach(() => {
    sessionStorage.clear()
    vi.mocked(api.randomQueries).mockResolvedValue({ questions: [] })
    vi.mocked(api.getChatAttachment).mockResolvedValue({
      attachment: {
        id: 'att-1',
        session_id: 's',
        filename: 'f.txt',
        display_name: 'f.txt',
        mime_type: 'text/plain',
        size_bytes: 1,
        status: 'READY',
      },
    } as never)
  })

  async function submitViaComposer(text: string) {
    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText(appConfig.chatPlaceholder), { target: { value: text } })
    })
    const send = await screen.findByRole('button', { name: 'Send question' })
    await waitFor(() => expect(send.hasAttribute('disabled')).toBe(false))
    await act(async () => {
      fireEvent.click(send)
    })
  }

  it('loads starter questions and submits one directly on click', async () => {
    vi.mocked(api.models).mockResolvedValue({ models: [{ provider: 'qwen', id: 'qwen-model', label: 'Qwen Private', available: true, reason: null }] })
    vi.mocked(api.randomQueries).mockResolvedValue({ questions: [
      { id: 'sales-1', question: 'Berapa total Gross Billing Value?', domain: 'sales', domains: ['sales'], difficulty: 'simple', analysis_type: 'metric', expected_visualization: 'kpi' },
      { id: 'sales-2', question: 'Produk apa yang paling laku Q4 2024?', domain: 'sales', domains: ['sales'], difficulty: 'simple', analysis_type: 'ranking', expected_visualization: 'bar' },
      { id: 'stock-1', question: 'Berapa stok gudang Tempo bulan Desember?', domain: 'stock', domains: ['stock'], difficulty: 'simple', analysis_type: 'metric', expected_visualization: 'kpi' },
    ] })
    vi.mocked(api.chatStream).mockImplementation((async function* () {
      yield { type: 'progress', stage: 'querying_data', label: 'Querying TEMPO data' }
      yield { type: 'done', response: {
        request_id: 'r1', session_id: 's1', status: 'SUCCESS', provider: 'qwen', model: 'qwen-model', strategy: 'governed',
        answer: { direct_answer: 'Rp10', executive_summary: 'Total Rp10', insights: [], business_implications: [], caveats: [], data_reference: 'result', chart_spec: { type: 'kpi', title: 'Total Sales', y: 'value' } },
        data: { columns: ['value'], rows: [{ value: 10 }], row_count: 1, execution_ms: 1 }, chart_spec: { type: 'kpi', title: 'Total Sales', y: 'value' },
        timings: { context_ms: 1, planning_ms: 1, validation_ms: 1, query_ms: 1, analysis_ms: 1, total_ms: 6 }, retry_count: 0,
      } }
    }) as never)
    renderWithProviders(<AskDataPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Berapa total Gross Billing Value?' }))

    expect((await screen.findAllByText('Total Rp10')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Total Sales').length).toBeGreaterThan(0)
    await waitFor(() => expect(api.chatStream).toHaveBeenCalledWith(
      'Berapa total Gross Billing Value?',
      expect.any(String),
      { provider: 'qwen', model: 'qwen-model' },
      expect.any(AbortSignal),
      expect.objectContaining({ mode: 'ask_data' }),
    ))
  })

  it('presents the direct answer, implications, and data reference with clear hierarchy', async () => {
    vi.mocked(api.models).mockResolvedValue({ models: [{ provider: 'qwen', id: 'qwen-model', label: 'Qwen Private', available: true, reason: null }] })
    vi.mocked(api.randomQueries).mockResolvedValue({
      questions: [{
        id: 'sales-q4',
        question: 'Berapa gross sales Q4?',
        domain: 'sales',
        domains: ['sales'],
        difficulty: 'simple',
        analysis_type: 'metric',
        expected_visualization: 'kpi',
      }],
    })
    vi.mocked(api.chatStream).mockImplementation((async function* () {
      yield { type: 'progress', stage: 'querying_data', label: 'Querying TEMPO data' }
      yield { type: 'done', response: {
        request_id: 'r2', session_id: 's2', status: 'SUCCESS', provider: 'qwen', model: 'qwen-model', strategy: 'governed', route: 'ask_data',
        answer: { direct_answer: 'Gross Sales Q4 sebesar Rp10 miliar.', executive_summary: 'Nilai ini merupakan akumulasi Oktober–Desember.', insights: ['Desember tertinggi.'], business_implications: ['Prioritaskan ketersediaan stok Desember.'], caveats: ['Data hanya Q4 2024.'], data_reference: 'gold.rpt_sap_monthly_executive_semantic', chart_spec: null },
        data: { columns: [], rows: [], row_count: 0, execution_ms: 1 }, chart_spec: null,
        timings: { context_ms: 1, planning_ms: 1, validation_ms: 1, query_ms: 1, analysis_ms: 1, total_ms: 6 }, retry_count: 0,
      } }
    }) as never)
    renderWithProviders(<AskDataPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Berapa gross sales Q4?' }))
    await waitFor(() => expect(api.chatStream).toHaveBeenCalledWith(
      'Berapa gross sales Q4?',
      expect.any(String),
      { provider: 'qwen', model: 'qwen-model' },
      expect.any(AbortSignal),
      expect.objectContaining({ mode: 'ask_data' }),
    ))
    await waitFor(() => expect(screen.getByText('Berapa gross sales Q4?')).toBeTruthy())
  })

  it('collapses the primary sidebar from the sidebar toggle', async () => {
    vi.mocked(api.models).mockResolvedValue({ models: [{ provider: 'qwen', id: 'qwen-model', label: 'Qwen Private', available: true, reason: null }] })
    renderWithProviders(
      <AppShell>
        <AskDataPage />
      </AppShell>,
    )

    const navigation = screen.getByLabelText('Primary sidebar')
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'New chat' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))

    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeTruthy()
    expect(navigation.className).toContain('lg:w-[68px]')

    fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }))
    expect(navigation.className).toContain('lg:w-[272px]')
  })

  it('lets the user stop a request that is still loading', async () => {
    vi.mocked(api.models).mockResolvedValue({ models: [{ provider: 'qwen', id: 'qwen-model', label: 'Qwen Private', available: true, reason: null }] })
    vi.mocked(api.chatStream).mockImplementation((async function* (_question, _session, _selection, signal?: AbortSignal) {
      yield { type: 'progress', stage: 'querying_data', label: 'Querying TEMPO data' }
      await new Promise<void>((_resolve, reject) => signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true }))
    }) as never)
    renderWithProviders(<AskDataPage />)

    await submitViaComposer('Berapa fill rate?')
    fireEvent.click(await screen.findByRole('button', { name: 'Stop request' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop request' })).toBeNull())
    expect(screen.getByText('Request stopped.')).toBeTruthy()
  })

  it('downloads the visible conversation as PDF after a completed answer', async () => {
    vi.mocked(api.models).mockResolvedValue({ models: [{ provider: 'qwen', id: 'qwen-model', label: 'Qwen Private', available: true, reason: null }] })
    vi.mocked(api.chatStream).mockImplementation((async function* () {
      yield { type: 'progress', stage: 'querying_data', label: 'Querying TEMPO data' }
      yield { type: 'done', response: {
        request_id: 'r-dl', session_id: 's-dl', status: 'SUCCESS', provider: 'qwen', model: 'qwen-model', strategy: 'governed', route: 'ask_data',
        answer: { direct_answer: 'Done.', executive_summary: 'Done.', insights: [], business_implications: [], caveats: [], data_reference: 'gold.table', chart_spec: null },
        data: { columns: [], rows: [], row_count: 0, execution_ms: 1 }, chart_spec: null,
        timings: { total_ms: 5 }, retry_count: 0,
      } }
    }) as never)
    renderWithProviders(
      <AppShell>
        <AskDataPage />
      </AppShell>,
    )
    await submitViaComposer('Test export?')
    await waitFor(() => expect(api.chatStream).toHaveBeenCalled())
    await waitFor(() => expect(screen.getAllByText('Done.').length).toBeGreaterThan(0))
    await waitFor(async () => {
      const downloadButton = screen.getByRole('button', { name: 'Download conversation as PDF' })
      expect(downloadButton.hasAttribute('disabled')).toBe(false)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Download conversation as PDF' }))

    await waitFor(() => expect(downloadConversationPdf).toHaveBeenCalled())
  })

  it('does not auto-submit a second request after the stream completes', async () => {
    vi.mocked(api.models).mockResolvedValue({ models: [{ provider: 'qwen', id: 'qwen-model', label: 'Qwen Private', available: true, reason: null }] })
    vi.mocked(api.chatStream).mockImplementation((async function* () {
      yield { type: 'progress', stage: 'querying_data', label: 'Querying TEMPO data' }
      yield { type: 'done', response: {
        request_id: 'r-once', session_id: 's-once', status: 'SUCCESS', provider: 'qwen', model: 'qwen-model', strategy: 'governed', route: 'ask_data',
        answer: { direct_answer: 'Once.', executive_summary: 'Once.', insights: [], business_implications: [], caveats: [], data_reference: 't', chart_spec: null },
        data: { columns: [], rows: [], row_count: 0, execution_ms: 1 }, chart_spec: null,
        timings: { total_ms: 5 }, retry_count: 0,
      } }
    }) as never)
    renderWithProviders(<AskDataPage />)
    await submitViaComposer('Single turn?')
    await waitFor(() => expect(api.chatStream).toHaveBeenCalled())
    await waitFor(() => expect(screen.getAllByText('Once.').length).toBeGreaterThan(0))

    await waitFor(() => expect(api.chatStream).toHaveBeenCalledTimes(1))
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50))
    })
    expect(api.chatStream).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Understanding your question')).toBeNull()
  })

  it('times out a request and clears its loading state after 90 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(api.models).mockResolvedValue({ models: [{ provider: 'qwen', id: 'qwen-model', label: 'Qwen Private', available: true, reason: null }] })
    vi.mocked(api.chatStream).mockImplementation((async function* (_question, _session, _selection, signal?: AbortSignal) {
      yield { type: 'progress', stage: 'querying_data', label: 'Querying TEMPO data' }
      await new Promise<void>((_resolve, reject) => signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true }))
    }) as never)
    renderWithProviders(<AskDataPage />)

    await submitViaComposer('Berapa fill rate?')
    await screen.findByRole('button', { name: 'Stop request' })
    await act(async () => { await vi.advanceTimersByTimeAsync(190_000) })

    expect(screen.queryByRole('button', { name: 'Stop request' })).toBeNull()
    expect(screen.getByText('Request timed out. Please try again.')).toBeTruthy()
  })
})
