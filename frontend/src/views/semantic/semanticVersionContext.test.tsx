import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SemanticVersionContextBar } from './SemanticVersionContextBar'

const active = {
  id: 'v2',
  semantic_model_id: 'm1',
  version_number: 2,
  status: 'ACTIVE',
} as const

const draft = {
  id: 'v3',
  semantic_model_id: 'm1',
  version_number: 3,
  status: 'DRAFT',
} as const

describe('SemanticVersionContextBar', () => {
  afterEach(cleanup)

  it('shows editing pill and live published hint', () => {
    render(
      <SemanticVersionContextBar
        draftVersion={draft as never}
        activeVersion={active as never}
        isEditable
        needsRuntimeActivation={false}
        publishNeedsAttention={false}
        statusPill={{ label: 'Editing · v3', className: 'bg-violet-100 text-violet-900' }}
      />,
    )
    expect(screen.getByTestId('semantic-header-status-badge').textContent).toMatch(/Editing · v3/)
    expect(screen.getByTestId('semantic-version-live-badge').textContent).toMatch(/v2/)
    expect(screen.queryByTestId('semantic-discard-draft')).toBeNull()
  })

  it('shows draft saved pill and discard link when not editing', () => {
    render(
      <SemanticVersionContextBar
        draftVersion={draft as never}
        activeVersion={active as never}
        isEditable={false}
        needsRuntimeActivation={false}
        publishNeedsAttention={false}
        statusPill={{ label: 'Draft saved · v3', className: 'bg-slate-100 text-slate-800' }}
        onDiscardDraft={vi.fn()}
      />,
    )
    expect(screen.getByTestId('semantic-header-status-badge').textContent).toMatch(/Draft saved/)
    expect(screen.getByTestId('semantic-discard-draft')).toBeTruthy()
  })

  it('shows published detail when viewing published only', () => {
    render(
      <SemanticVersionContextBar
        draftVersion={null}
        activeVersion={active as never}
        isEditable={false}
        needsRuntimeActivation={false}
        publishNeedsAttention={false}
        statusPill={{ label: 'Published v2', className: 'bg-emerald-50 text-emerald-800' }}
      />,
    )
    expect(screen.getByTestId('semantic-version-context-detail').textContent).toMatch(/published v2/)
  })
})
