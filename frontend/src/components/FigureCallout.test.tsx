import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { FigureCallout, singleFigure } from './FigureCallout'
import type { ChatResponse } from '../types/api'

const answer = (data: Partial<ChatResponse['data']>, extra: Partial<ChatResponse> = {}) =>
  ({
    status: 'SUCCESS',
    strategy: 'governed',
    data: { columns: ['metric_value'], rows: [{ metric_value: 16.07 }], row_count: 1, execution_ms: 1, governed_metric: 'tingkat_keterlambatan', governed_metric_display_name: 'Tingkat Keterlambatan', unit_format: 'percent', ...data },
    ...extra,
  }) as unknown as ChatResponse

describe('FigureCallout', () => {
  afterEach(cleanup)

  it('adds only how the figure stands against its target, not the figure again, red when lower is better and it is above', () => {
    const response = answer({ metric_target: 15, metric_better: 'down' })
    render(<FigureCallout response={response} value={singleFigure(response)!} />)
    const line = screen.getByTestId('figure-callout')
    expect(line.textContent).toContain('Target 15%')
    expect(line.textContent).not.toContain('16.07') // the answer sentence already says it
    expect(screen.getByText('1.07 pts above target').className).toContain('text-rose-700')
  })

  it('shows nothing when the model declares no target', () => {
    const response = answer({})
    const { container } = render(<FigureCallout response={response} value={singleFigure(response)!} />)
    expect(container.textContent).toBe('')
  })

  it('states the gap without judging it when the model does not say which way is better', () => {
    const response = answer({ metric_target: 15 })
    render(<FigureCallout response={response} value={singleFigure(response)!} />)
    expect(screen.getByText('1.07 pts above target').className).toContain('text-slate-800')
  })

  it('applies only to one number: not to a breakdown, an agent report or a failed answer', () => {
    expect(singleFigure(answer({}))).toBe(16.07)
    expect(singleFigure(answer({ columns: ['regional', 'metric_value'], rows: [{ regional: 'A', metric_value: 1 }, { regional: 'B', metric_value: 2 }] }))).toBeNull()
    expect(singleFigure(answer({}, { strategy: 'agent' }))).toBeNull()
    expect(singleFigure(answer({}, { status: 'NO_DATA' }))).toBeNull()
  })

  it('writes numbers the way the answer does: 1,07 under an Indonesian answer', () => {
    const response = answer({ metric_target: 15, metric_better: 'down' }, { language: 'id' })
    render(<FigureCallout response={response} value={singleFigure(response)!} />)
    expect(screen.getByText('1,07 pts above target')).toBeTruthy()
  })
})
