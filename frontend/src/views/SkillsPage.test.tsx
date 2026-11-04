import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../lib/api'
import { SkillsPage } from './SkillsPage'

vi.mock('../lib/api', () => ({
  api: {
    listSkills: vi.fn(),
    listTools: vi.fn(),
    listSkillVersions: vi.fn(),
    createSkill: vi.fn(),
    createSkillVersion: vi.fn(),
    publishSkillVersion: vi.fn(),
    executeSkill: vi.fn(),
  },
}))

describe('Skills page', () => {
  afterEach(cleanup)

  it('publishes a new skill straight from the create drawer and closes it', async () => {
    const record = { id: 's1', name: 'Summarise', key: 'summarise', scope: 'global', status: 'DRAFT', updated_at: '2026-01-01T00:00:00Z' }
    const draft = { id: 'v1', version_number: 1, status: 'DRAFT', instructions: 'x', allowed_tools: [], config: {}, created_at: '2026-01-01T00:00:00Z' }
    vi.mocked(api.listSkills).mockResolvedValueOnce({ skills: [] } as never).mockResolvedValue({ skills: [record] } as never)
    vi.mocked(api.listTools).mockResolvedValue({ tools: [] } as never)
    vi.mocked(api.createSkill).mockResolvedValue({ skill: record } as never)
    vi.mocked(api.listSkillVersions).mockResolvedValue({ versions: [draft] } as never)
    vi.mocked(api.publishSkillVersion).mockResolvedValue({ version: { ...draft, status: 'ACTIVE' } } as never)
    render(<SkillsPage />)
    fireEvent.click(await screen.findByRole('button', { name: /New skill/i }))
    expect(screen.getByRole('button', { name: 'Publish' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/Display name/i), { target: { value: 'Summarise' } })
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }))
    await waitFor(() => expect(api.publishSkillVersion).toHaveBeenCalledWith('s1', 'v1'))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save draft' })).toBeNull())
  })
})
