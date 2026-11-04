import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../../lib/api'
import { renderWithProviders } from '../../test/renderWithProviders'
import { AiModelsSettingsPanel } from './AiModelsSettingsPanel'

vi.mock('../../lib/api', () => ({
  api: {
    listAiProviders: vi.fn(),
    listAiModels: vi.fn(),
    listModelAssignments: vi.fn(),
    listAiProviderRemoteModels: vi.fn(),
    createAiProvider: vi.fn(),
    testAiProvider: vi.fn(),
    putModelAssignment: vi.fn(),
    deleteModelAssignment: vi.fn(),
    listEnvironmentReferences: vi.fn(async () => ({ references: [] })),
  },
}))

describe('AiModelsSettingsPanel', () => {
  afterEach(cleanup)

  it('shows empty state when no providers', async () => {
    vi.mocked(api.listAiProviders).mockResolvedValue({ providers: [] })
    vi.mocked(api.listAiModels).mockResolvedValue({ models: [] })
    vi.mocked(api.listModelAssignments).mockResolvedValue({
      assignments: [
        {
          capability: 'ASK_DATA',
          model_id: null,
          model_name: null,
          model_key: null,
          provider_type: null,
          enabled: false,
          source: 'LEGACY_FALLBACK',
          health: 'NOT_CONFIGURED',
        },
      ],
    })
    renderWithProviders(<AiModelsSettingsPanel />)
    expect(await screen.findByText(/Register your first AI provider/i)).toBeTruthy()
    expect(await screen.findByRole('heading', { name: 'Runtime assignments' })).toBeTruthy()
    expect(screen.getByText('Default Chat')).toBeTruthy()
  })

  it('lists providers and filters assignment models', async () => {
    vi.mocked(api.listAiProviders).mockResolvedValue({
      providers: [
        {
          id: 'p1',
          name: 'Gemini Prod',
          key: 'gemini_prod',
          provider_type: 'GEMINI',
          base_url: null,
          secret_ref: 'env://GEMINI_API_KEY',
          secret_configured: true,
          enabled: true,
          status: 'READY',
          config_json: {},
          last_test_at: null,
          created_at: '',
          updated_at: '',
        },
      ],
    })
    vi.mocked(api.listAiModels).mockResolvedValue({
      models: [
        {
          id: 'm1',
          provider_id: 'p1',
          name: 'Flash',
          key: 'flash',
          model_id: 'gemini-3.8-flash',
          model_type: 'CHAT',
          enabled: true,
          capabilities: { streaming: null, tools: null, json_mode: null, vision: null },
          context_window: null,
          max_output_tokens: null,
          provider_type: 'GEMINI',
          status: 'READY',
          config_json: {},
          last_test_at: null,
        },
      ],
    })
    vi.mocked(api.listModelAssignments).mockResolvedValue({
      assignments: [
        {
          capability: 'ASK_DATA',
          model_id: 'm1',
          model_name: 'Flash',
          model_key: 'flash',
          provider_type: 'GEMINI',
          enabled: true,
          source: 'PROJECT',
          health: 'READY',
        },
      ],
    })
    renderWithProviders(<AiModelsSettingsPanel />)
    expect((await screen.findAllByText('Gemini Prod')).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Project assignment/i).length).toBeGreaterThan(0)
    expect(screen.queryByText(/env:\/\/GEMINI_API_KEY/i)).toBeNull()
  })

  it('paginates registered models table (default 5 per page)', async () => {
    vi.mocked(api.listAiProviders).mockResolvedValue({
      providers: [
        {
          id: 'p1',
          name: 'Gemini Prod',
          key: 'gemini_prod',
          provider_type: 'GEMINI',
          base_url: null,
          secret_ref: null,
          secret_configured: true,
          enabled: true,
          status: 'READY',
          config_json: {},
          last_test_at: null,
          created_at: '',
          updated_at: '',
        },
      ],
    })
    vi.mocked(api.listAiModels).mockResolvedValue({
      models: Array.from({ length: 11 }, (_, i) => ({
        id: `m${i}`,
        provider_id: 'p1',
        name: `Model ${i}`,
        key: `model_${i}`,
        model_id: `gemini-${i}`,
        model_type: 'CHAT' as const,
        enabled: true,
        capabilities: { streaming: null, tools: null, json_mode: null, vision: null },
        context_window: null,
        max_output_tokens: null,
        provider_type: 'GEMINI' as const,
        status: 'READY',
        config_json: {},
        last_test_at: null,
      })),
    })
    vi.mocked(api.listModelAssignments).mockResolvedValue({ assignments: [] })
    renderWithProviders(<AiModelsSettingsPanel />)
    expect(await screen.findByText(/Showing 1–5 of 11/)).toBeTruthy()
    expect(screen.getByText('gemini-0')).toBeTruthy()
    expect(screen.queryByText('gemini-5')).toBeNull()
  })

  it('registers an OpenAI-compatible endpoint with a base URL and a key made from the name', async () => {
    vi.mocked(api.listAiProviders).mockResolvedValue({ providers: [] })
    vi.mocked(api.listAiModels).mockResolvedValue({ models: [] })
    vi.mocked(api.listModelAssignments).mockResolvedValue({ assignments: [] })
    vi.mocked(api.createAiProvider).mockResolvedValue({ provider: { id: 'p9' } } as never)
    renderWithProviders(<AiModelsSettingsPanel />)
    fireEvent.click((await screen.findAllByRole('button', { name: /Register provider/i }))[0]!)
    fireEvent.click(await screen.findByText('OpenAI Compatible'))
    fireEvent.change(screen.getByPlaceholderText('Google Gemini (local)'), { target: { value: 'qwen-35-9b' } })
    fireEvent.change(screen.getByPlaceholderText('https://your-endpoint.example.com/v1'), {
      target: { value: 'https://vllm-qwen35.example.cloudera.site/v1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.createAiProvider).toHaveBeenCalled())
    expect(vi.mocked(api.createAiProvider).mock.calls[0]![0]).toMatchObject({
      name: 'qwen-35-9b',
      key: 'qwen_35_9b',
      provider_type: 'OPENAI_COMPATIBLE',
      base_url: 'https://vllm-qwen35.example.cloudera.site/v1',
    })
  })
})
