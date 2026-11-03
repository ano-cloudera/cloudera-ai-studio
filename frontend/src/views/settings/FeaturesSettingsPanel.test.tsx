import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { appConfig } from '../../config/appConfig'
import { setFeatureOverrides, getFeatureOverrides } from '../../lib/featureOverrides'
import { FeaturesSettingsPanel, nextOverrides } from './FeaturesSettingsPanel'

const put = vi.fn()
vi.mock('../../lib/api', () => ({ api: { putFeatureOverrides: (...args: unknown[]) => put(...args) } }))

describe('nextOverrides', () => {
  const defaults = appConfig.deploymentFeatures
  it('stores a real change and drops the override when it matches the default again', () => {
    expect(nextOverrides({}, 'skills', true, defaults)).toEqual({ skills: true })
    expect(nextOverrides({ skills: true }, 'skills', false, defaults)).toEqual({}) // the default of skills is off
    expect(nextOverrides({ documents: false }, 'prompts', false, defaults)).toEqual({ documents: false, prompts: false })
  })
})

describe('FeaturesSettingsPanel', () => {
  beforeEach(() => {
    put.mockReset()
    put.mockImplementation(async (overrides: object) => ({ overrides }))
  })
  afterEach(() => {
    cleanup()
    setFeatureOverrides({}, { cache: false })
  })

  it('shows Ask Data, Settings, Semantic Layer, Data Sources and Usage as always on, with no switch', () => {
    render(<FeaturesSettingsPanel />)
    const rows = within(screen.getByTestId('feature-list')).getAllByRole('listitem')
    for (const label of ['Ask Data', 'Settings', 'Semantic Layer', 'Data Sources', 'Usage']) {
      const row = rows.find(item => item.textContent?.includes(label))!
      expect(within(row).getByText('Always on')).toBeTruthy()
      expect(within(row).queryByRole('switch')).toBeNull()
    }
    expect(screen.getAllByRole('switch').map(item => item.getAttribute('aria-label'))).toEqual(['Knowledge on', 'Prompts on', 'Skills off'])
    expect(screen.getByText(/does not restrict access to the API/)).toBeTruthy()
  })

  it('switches a feature, saves it and marks it as changed from the default', async () => {
    render(<FeaturesSettingsPanel />)
    fireEvent.click(screen.getByRole('switch', { name: 'Skills off' }))
    await waitFor(() => expect(put).toHaveBeenCalledWith({ skills: true }))
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Skills on' })).toBeTruthy())
    expect(screen.getByText('Changed from default (Off)')).toBeTruthy()
    expect(getFeatureOverrides()).toEqual({ skills: true })
  })

  it('puts the switch back and says why when the server refuses', async () => {
    put.mockRejectedValue(new Error('read-only database'))
    render(<FeaturesSettingsPanel />)
    fireEvent.click(screen.getByRole('switch', { name: 'Prompts on' }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('read-only database'))
    expect(screen.getByRole('switch', { name: 'Prompts on' })).toBeTruthy()
    expect(getFeatureOverrides()).toEqual({})
  })

  it('explains why a locked feature has no switch, and resets every change', async () => {
    render(<FeaturesSettingsPanel />)
    expect(screen.getByText('Ask Data answers from its published models.')).toBeTruthy()
    const reset = screen.getByRole('button', { name: 'Reset to deployment defaults' }) as HTMLButtonElement
    expect(reset.disabled).toBe(true) // nothing to reset yet
    act(() => setFeatureOverrides({ prompts: false, skills: true }, { cache: false }))
    expect(reset.disabled).toBe(false)
    fireEvent.click(reset)
    await waitFor(() => expect(put).toHaveBeenCalledWith({}))
    await waitFor(() => expect(getFeatureOverrides()).toEqual({}))
  })
})
