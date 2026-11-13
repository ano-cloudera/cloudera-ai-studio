import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_PRESENTATION } from '../../lib/presentationPresets'
import { AskDataPresentationSettingsPanel } from './AskDataPresentationSettingsPanel'

vi.mock('../../lib/api', () => ({
  api: {
    getAskDataSettings: vi.fn(),
    askDataPresentationConfig: vi.fn(),
    putAskDataSettings: vi.fn(),
  },
}))

const baseSettings = { default_semantic_model_id: null, auto_attach_semantic_model: true }

describe('AskDataPresentationSettingsPanel', () => {
  beforeEach(async () => {
    const { api } = await import('../../lib/api')
    vi.mocked(api.getAskDataSettings).mockResolvedValue({ settings: baseSettings } as never)
    vi.mocked(api.askDataPresentationConfig).mockResolvedValue({ presentation: DEFAULT_PRESENTATION } as never)
    vi.mocked(api.putAskDataSettings).mockResolvedValue({} as never)
  })
  afterEach(cleanup)

  it('explains the settings in plain words and starts on the Demo preset', async () => {
    render(<AskDataPresentationSettingsPanel />)
    expect(await screen.findByText('How answers are shown')).toBeTruthy()
    expect(screen.getByRole('radio', { name: /Demo/ }).getAttribute('aria-checked')).toBe('true')
    expect(screen.queryByText(/tier/i)).toBeNull() // no internal vocabulary on the screen
    expect(screen.getByText('What you will see')).toBeTruthy()
  })

  it('a preset changes the preview at once and is saved as the overrides', async () => {
    const { api } = await import('../../lib/api')
    render(<AskDataPresentationSettingsPanel />)
    fireEvent.click(await screen.findByRole('radio', { name: /Analyst workbench/ }))
    expect(screen.getByRole('radio', { name: /Analyst workbench/ }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getAllByText(/analysis panel \(chart, table, SQL\) opens/).length).toBe(4)
    fireEvent.click(screen.getByRole('button', { name: 'Save for this workspace' }))
    await waitFor(() => expect(api.putAskDataSettings).toHaveBeenCalled())
    const body = vi.mocked(api.putAskDataSettings).mock.calls[0][0] as { presentation: Record<string, unknown> }
    expect(body.presentation).toMatchObject({ audience_mode: 'analyst', panel_auto_open: 'always', chat_details_default_open: true })
  })

  it('shows custom when the choices match no preset and resets to the defaults', async () => {
    render(<AskDataPresentationSettingsPanel />)
    fireEvent.click(await screen.findByLabelText(/Add a short explanation/))
    expect(screen.getAllByRole('radio').every(radio => radio.getAttribute('aria-checked') === 'false')).toBe(true)
    expect(screen.getByText(/shown as custom/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    expect(screen.getByRole('radio', { name: /Demo/ }).getAttribute('aria-checked')).toBe('true')
  })

  it('offers only the choices a person understands: no size thresholds to tune', async () => {
    render(<AskDataPresentationSettingsPanel />)
    await screen.findByText('How answers are shown')
    expect(screen.queryByLabelText(/What counts as a bigger answer/)).toBeNull()
    expect(screen.queryByText('Advanced settings')).toBeNull()
    expect(screen.getByLabelText(/When does the analysis panel open/)).toBeTruthy()
  })
})
