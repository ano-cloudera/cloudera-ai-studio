import { describe, expect, it } from 'vitest'
import { chartViews, differenceRows, paretoRows } from './chartViews'

const base = { hasSeries: false, timeOnX: false }

describe('chartViews', () => {
  it('gives at most two views, the second only when the data supports it honestly', () => {
    expect(chartViews({ ...base, type: 'bar', values: [5, 3, 2], unitFormat: 'quantity' }).map(v => v.id)).toEqual(['native', 'pie'])
    expect(chartViews({ ...base, type: 'bar', values: [9, 8, 7, 6, 5, 4, 3, 2], unitFormat: 'quantity' }).map(v => v.id)).toEqual(['native', 'pareto'])
    expect(chartViews({ ...base, type: 'bar', values: [34.5, 11.4], unitFormat: 'percent', overall: 16.07 }).map(v => v.id)).toEqual(['native', 'vs_overall'])
    expect(chartViews({ ...base, type: 'bar', values: [34.5, 11.4], unitFormat: 'percent' }).map(v => v.id)).toEqual(['native'])
    expect(chartViews({ ...base, type: 'bar', values: [5, 3], unitFormat: null }).map(v => v.id)).toEqual(['native']) // unknown unit: no guessed share
    expect(chartViews({ ...base, type: 'line', values: [1, 2, 3], unitFormat: 'percent', timeOnX: true }).map(v => v.id)).toEqual(['native', 'bar'])
    expect(chartViews({ ...base, type: 'bar', values: [1, 2, 3], unitFormat: 'quantity', hasSeries: true }).map(v => v.id)).toEqual(['native', 'stacked'])
    expect(chartViews({ ...base, type: 'bar', values: [1, 2, 3], unitFormat: 'quantity', timeOnX: true }).map(v => v.id)).toEqual(['native', 'line'])
  })

  it('computes the Pareto running share and each group against the overall value', () => {
    const pareto = paretoRows([{ p: 'b', v: 25 }, { p: 'a', v: 75 }], 'p', 'v')
    expect(pareto.map(r => r.__cumulative)).toEqual([75, 100])
    const diff = differenceRows([{ r: 'x', v: 11.4 }, { r: 'y', v: 34.54 }], 'r', 'v', 16.07)
    expect(diff).toEqual([{ r: 'y', __difference: 18.47 }, { r: 'x', __difference: -4.67 }])
  })
})
