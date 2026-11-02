import { describe, expect, it } from 'vitest'
import { workspaceColumnLabel } from './workspaceTableLabels'

describe('workspaceColumnLabel', () => {
  it('names the value column after the governed metric', () => {
    expect(workspaceColumnLabel('metric_value', 'total_applications')).toBe('Total Applications')
  })

  it('falls back to a neutral label when no metric is known', () => {
    expect(workspaceColumnLabel('metric_value')).toBe('Value')
  })

  it('keeps humanized labels for other columns', () => {
    expect(workspaceColumnLabel('region_name', 'total_applications')).toBe('Region Name')
  })

  it('labels the comparison columns', () => {
    expect(workspaceColumnLabel('previous_value')).toBe('Earlier period')
    expect(workspaceColumnLabel('change_pct')).toBe('Change (%)')
    expect(workspaceColumnLabel('difference')).toBe('Difference vs overall')
  })
})
