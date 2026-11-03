import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CreateSemanticModelWizard } from './CreateSemanticModelWizard'

vi.mock('../../lib/api', () => ({ api: { createSemanticModel: vi.fn() } }))

describe('wizard step 1: the model name', () => {
  afterEach(cleanup)

  it('explains the key, tidies a key-like name when you leave the field, and shows the key that will be used', () => {
    render(<CreateSemanticModelWizard open connectors={[]} onClose={() => undefined} onCreated={() => undefined} />)
    const input = screen.getByPlaceholderText('Commercial Sales') as HTMLInputElement
    expect(screen.getByTestId('wizard-key-hint').textContent).toContain('readable name')
    fireEvent.change(input, { target: { value: 'fulfillment_delivery' } })
    expect(screen.getByTestId('wizard-key-hint').textContent).toBe('Key: fulfillment_delivery (made from the name, used internally)')
    fireEvent.blur(input)
    expect(input.value).toBe('Fulfillment Delivery')
    expect(screen.getByTestId('wizard-key-hint').textContent).toContain('Key: fulfillment_delivery')
  })

  it('leaves a name written with spaces as it is', () => {
    render(<CreateSemanticModelWizard open connectors={[]} onClose={() => undefined} onCreated={() => undefined} />)
    const input = screen.getByPlaceholderText('Commercial Sales') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'Sales Performance' } })
    fireEvent.blur(input)
    expect(input.value).toBe('Sales Performance')
    expect(screen.getByTestId('wizard-key-hint').textContent).toContain('Key: sales_performance')
  })
})
