import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const references = [
  { name: 'TRINO_PASSWORD', ref: 'env://TRINO_PASSWORD', kind: 'password' },
  { name: 'GEMINI_API_KEY', ref: 'env://GEMINI_API_KEY', kind: 'api_key' },
]

async function load(listing: () => Promise<{ references: typeof references }>) {
  vi.resetModules()
  vi.doMock('../lib/api', () => ({ api: { listEnvironmentReferences: listing } }))
  return (await import('./EnvRefSelect')).EnvRefSelect
}

describe('EnvRefSelect', () => {
  beforeEach(() => vi.resetModules())
  afterEach(() => {
    cleanup()
    vi.doUnmock('../lib/api')
  })

  it('offers the available variables, api keys first, and reports the chosen reference', async () => {
    const Select = await load(async () => ({ references }))
    const onChange = vi.fn()
    render(<Select value="" onChange={onChange} />)
    const select = await screen.findByRole('combobox')
    const labels = Array.from(select.querySelectorAll('option')).map(option => option.textContent)
    expect(labels).toEqual(['Choose a variable…', 'GEMINI_API_KEY', 'TRINO_PASSWORD', 'Other (type a name)…'])
    fireEvent.change(select, { target: { value: 'env://TRINO_PASSWORD' } })
    expect(onChange).toHaveBeenCalledWith('env://TRINO_PASSWORD')
  })

  it('lets the user type another name', async () => {
    const Select = await load(async () => ({ references }))
    const onChange = vi.fn()
    render(<Select value="" onChange={onChange} />)
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: '__custom__' } })
    const input = await screen.findByPlaceholderText('env://NAME')
    fireEvent.change(input, { target: { value: 'env://MY_SECRET' } })
    expect(onChange).toHaveBeenLastCalledWith('env://MY_SECRET')
  })

  it('shows a saved reference that is not in the list as typed text', async () => {
    const Select = await load(async () => ({ references }))
    render(<Select value="env://OLD_SECRET" onChange={() => undefined} />)
    expect(((await screen.findByPlaceholderText('env://NAME')) as HTMLInputElement).value).toBe('env://OLD_SECRET')
  })

  it('falls back to typing, with a hint, when the list cannot be loaded', async () => {
    const Select = await load(async () => {
      throw new Error('offline')
    })
    render(<Select value="" onChange={() => undefined} />)
    await waitFor(() => expect(screen.getByPlaceholderText('env://NAME')).toBeTruthy())
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.getByText(/No credential variables were found/)).toBeTruthy()
  })
})
