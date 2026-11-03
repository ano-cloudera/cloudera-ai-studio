import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AskDataSettingsPayload } from '../../types/api'
import { AskDataGovernedScopeSettingsPanel, applyDefaultModelChoice, defaultModelChoice } from './AskDataGovernedScopeSettingsPanel'

const listSemanticModels = vi.fn()
vi.mock('../../lib/api', () => ({ api: { listSemanticModels: (...args: unknown[]) => listSemanticModels(...args) } }))

const base = { auto_attach_semantic_model: true, default_semantic_model_id: null } as AskDataSettingsPayload
const model = (id: string, name: string, active = 'v1') => ({ id, name, key: name, active_version_id: active })

describe('default model choice', () => {
  it('maps the three outcomes to the two stored fields and back', () => {
    expect(defaultModelChoice(base)).toBe('')
    expect(defaultModelChoice({ ...base, default_semantic_model_id: 'm1' })).toBe('m1')
    expect(defaultModelChoice({ ...base, auto_attach_semantic_model: false })).toBe('__none__')
    expect(applyDefaultModelChoice(base, 'm1')).toMatchObject({ auto_attach_semantic_model: true, default_semantic_model_id: 'm1' })
    expect(applyDefaultModelChoice(base, '')).toMatchObject({ auto_attach_semantic_model: true, default_semantic_model_id: null })
    expect(applyDefaultModelChoice({ ...base, default_semantic_model_id: 'm1' }, '__none__')).toMatchObject({
      auto_attach_semantic_model: false,
      default_semantic_model_id: null,
    })
  })
})

describe('AskDataGovernedScopeSettingsPanel', () => {
  afterEach(() => {
    cleanup()
    listSemanticModels.mockReset()
  })

  it('lists only published models and reports the choice', async () => {
    listSemanticModels.mockResolvedValue({ models: [model('m1', 'Fulfillment'), model('m2', 'Unpublished', '')] })
    const onChange = vi.fn()
    render(<AskDataGovernedScopeSettingsPanel settings={base} onChange={onChange} />)
    const select = (await screen.findByLabelText(/Default semantic model/)) as HTMLSelectElement
    await waitFor(() => expect(Array.from(select.options).map(o => o.textContent)).toContain('Fulfillment'))
    expect(Array.from(select.options).map(o => o.textContent)).not.toContain('Unpublished')
    fireEvent.change(select, { target: { value: 'm1' } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ default_semantic_model_id: 'm1', auto_attach_semantic_model: true }))
  })

  it('warns when nothing is published, when several are and "Automatic" cannot choose, and when the saved model is gone', async () => {
    listSemanticModels.mockResolvedValue({ models: [] })
    const first = render(<AskDataGovernedScopeSettingsPanel settings={base} onChange={() => undefined} />)
    expect(await screen.findByText(/No semantic model is published yet/)).toBeTruthy()
    first.unmount()

    listSemanticModels.mockResolvedValue({ models: [model('m1', 'A'), model('m2', 'B')] })
    const second = render(<AskDataGovernedScopeSettingsPanel settings={base} onChange={() => undefined} />)
    expect(await screen.findByText(/2 models are published/)).toBeTruthy()
    second.unmount()

    listSemanticModels.mockResolvedValue({ models: [model('m1', 'A')] })
    render(<AskDataGovernedScopeSettingsPanel settings={{ ...base, default_semantic_model_id: 'gone' }} onChange={() => undefined} />)
    expect((await screen.findByRole('note')).textContent).toContain('no longer published')
  })

  it('no longer asks for a prompt key', async () => {
    listSemanticModels.mockResolvedValue({ models: [] })
    render(<AskDataGovernedScopeSettingsPanel settings={base} onChange={() => undefined} />)
    await screen.findByText(/No semantic model is published yet/)
    expect(screen.queryByText(/prompt key/i)).toBeNull()
  })
})
