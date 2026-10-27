import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { PromptsPage } from './PromptsPage'
import { SkillsPage } from './SkillsPage'

const prompt: import('../types/api').PromptRecord = {
  id: 'p1',
  workspace_id: 'w1',
  project_id: null,
  name: 'Ask Data System Prompt',
  key: 'ask_data.system',
  scope: 'global',
  description: null,
  active_version_id: 'v1',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-17T00:00:00Z',
}

const skill: import('../types/api').SkillRecord = {
  id: 's1',
  workspace_id: 'w1',
  project_id: null,
  name: 'Ask Data Analyst',
  key: 'ask_data_analyst',
  scope: 'workspace',
  description: null,
  status: 'ACTIVE',
  active_version_id: 'sv1',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-17T00:00:00Z',
}

vi.mock('../lib/api', () => ({
  api: {
    listPrompts: vi.fn(),
    listPromptVersions: vi.fn(),
    createPrompt: vi.fn(),
    createPromptVersion: vi.fn(),
    publishPromptVersion: vi.fn(),
    resolvePrompt: vi.fn(),
    listSkills: vi.fn(),
    listSkillVersions: vi.fn(),
    listTools: vi.fn(),
    createSkill: vi.fn(),
    createSkillVersion: vi.fn(),
    publishSkillVersion: vi.fn(),
    executeSkill: vi.fn(),
  },
}))

describe('Prompts table-first UX', () => {
  afterEach(cleanup)

  it('renders table without permanent split editor', async () => {
    vi.mocked(api.listPrompts).mockResolvedValue({ prompts: [prompt] })
    vi.mocked(api.listPromptVersions).mockResolvedValue({
      versions: [{ id: 'v1', prompt_id: 'p1', version_number: 3, content: 'Hello', status: 'ACTIVE', created_by: null, created_at: prompt.updated_at }],
    })
    render(<PromptsPage />)
    await waitFor(() => screen.getByText('Ask Data System Prompt'))
    expect(screen.getByRole('columnheader', { name: /Name/i })).toBeTruthy()
    expect(screen.queryByRole('textbox', { name: /prompt content/i })).toBeNull()
    expect(screen.getByText('ask_data.system')).toBeTruthy()
  })

  it('opens editor drawer on Create prompt', async () => {
    vi.mocked(api.listPrompts).mockResolvedValue({ prompts: [] })
    render(<PromptsPage />)
    await waitFor(() => screen.getByText(/No prompts yet/i))
    fireEvent.click(screen.getByRole('button', { name: /Create prompt/i }))
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Create prompt' })).toBeTruthy()
    expect(screen.getByText('Display name')).toBeTruthy()
  })

  it('opens editor drawer on Edit', async () => {
    vi.mocked(api.listPrompts).mockResolvedValue({ prompts: [prompt] })
    vi.mocked(api.listPromptVersions).mockResolvedValue({
      versions: [{ id: 'v1', prompt_id: 'p1', version_number: 1, content: 'Body', status: 'DRAFT', created_by: null, created_at: prompt.updated_at }],
    })
    render(<PromptsPage />)
    await waitFor(() => screen.getByText('Ask Data System Prompt'))
    fireEvent.click(screen.getByRole('button', { name: 'Ask Data System Prompt' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('tab', { name: 'Editor' })).toBeTruthy()
    expect(within(dialog).getByDisplayValue('Body')).toBeTruthy()
  })
})

describe('Skills table-first UX', () => {
  afterEach(cleanup)

  it('renders table and formats handler as Ask Data', async () => {
    vi.mocked(api.listSkills).mockResolvedValue({ skills: [skill] })
    vi.mocked(api.listTools).mockResolvedValue({ tools: [] })
    vi.mocked(api.listSkillVersions).mockResolvedValue({
      versions: [
        {
          id: 'sv1',
          skill_id: 's1',
          version_number: 1,
          instructions: 'Do work',
          prompt_key: 'ask_data.system',
          input_schema: null,
          output_schema: null,
          allowed_tools: ['document_retrieval'],
          config: { handler_type: 'ask_data' },
          status: 'ACTIVE',
          created_at: skill.updated_at,
        },
      ],
    })
    render(<SkillsPage />)
    await waitFor(() => screen.getByText('Ask Data Analyst'))
    await waitFor(() => expect(screen.getByText('Ask Data')).toBeTruthy())
    expect(screen.queryByText('ask_data')).toBeNull()
  })

  it('opens configuration drawer for New skill', async () => {
    vi.mocked(api.listSkills).mockResolvedValue({ skills: [] })
    vi.mocked(api.listTools).mockResolvedValue({ tools: [] })
    render(<SkillsPage />)
    await waitFor(() => screen.getByText(/No skills yet/i))
    fireEvent.click(screen.getByRole('button', { name: /New skill/i }))
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Configuration' })).toBeTruthy()
  })
})
