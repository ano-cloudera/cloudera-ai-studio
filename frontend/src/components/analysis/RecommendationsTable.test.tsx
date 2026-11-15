import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { RecommendationsTable } from './RecommendationsTable'

const row = (over: Partial<Parameters<typeof RecommendationsTable>[0]['rows'][number]> = {}) => ({ priority: 'Tinggi', action: 'Buat tiket tindak lanjut prioritas tinggi', basis: 'Papua Maluku 34,54% vs 16,07%', owner: '', timeframe: '', source: '', ...over })

describe('RecommendationsTable', () => {
  afterEach(cleanup)

  it('shows what to do, why, who by when and where it is written, in one row each', () => {
    render(<RecommendationsTable rows={[row({ owner: 'Regional Distribution Manager', timeframe: '24 jam', source: 'SOP, hal. 1' }), row({ action: 'Tinjau mingguan', priority: 'Sedang', owner: 'Regional Distribution Manager', timeframe: 'mingguan' })]} />)
    const table = screen.getByTestId('recommendations-table')
    expect(table.textContent).toContain('Buat tiket tindak lanjut prioritas tinggi')
    expect(table.textContent).toContain('Regional Distribution Manager → 24 jam')
    expect(table.textContent).toContain('SOP, hal. 1')
    expect(screen.getByText('Tinggi').className).toContain('rose')
    expect(screen.getByText('Sedang').className).toContain('amber')
  })

  it('leaves out a column that no row fills, so there is no column of dashes', () => {
    render(<RecommendationsTable rows={[row()]} />)
    expect(screen.queryByText('Owner and timeframe')).toBeNull()
    expect(screen.queryByText('Source')).toBeNull()
    expect(screen.getByText('Basis')).toBeTruthy()
  })

  it('renders nothing for no rows', () => {
    const { container } = render(<RecommendationsTable rows={[]} />)
    expect(container.textContent).toBe('')
  })
})
