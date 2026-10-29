import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WorkspaceDataTable } from './WorkspaceDataTable'

describe('WorkspaceDataTable', () => {
  it('shows no rank column for a single value and labels it by metric', () => {
    render(
      <WorkspaceDataTable
        title="Total Applications"
        columns={['metric_value']}
        rows={[{ metric_value: 12000 }]}
        metric="total_applications"
      />,
    )
    expect(screen.queryByText('Rank')).toBeNull()
    expect(screen.getByRole('columnheader', { name: /Total Applications/ })).toBeTruthy()
    expect(screen.getByText('12,000')).toBeTruthy()
  })

  it('shows a left-aligned rank column when there are several rows', () => {
    render(
      <WorkspaceDataTable
        title="By segment"
        columns={['customer_segment', 'metric_value']}
        rows={[
          { customer_segment: 'Priority', metric_value: 4032 },
          { customer_segment: 'SME', metric_value: 4013 },
        ]}
        metric="total_applications"
      />,
    )
    const rankHeader = screen.getByRole('columnheader', { name: /Rank/ })
    expect(rankHeader.className).toContain('text-left')
    expect(rankHeader.className).not.toContain('text-center')
  })
})
