import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { Provider } from 'react-redux'
import { ModelSelectionBootstrap } from '../store/ModelSelectionBootstrap'
import { createAppStore } from '../store/store'
import { TestBrandingWrapper } from './testBrandingWrapper'

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  const store = createAppStore()
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <TestBrandingWrapper>
          <ModelSelectionBootstrap>{children}</ModelSelectionBootstrap>
        </TestBrandingWrapper>
      </Provider>
    )
  }
  return { store, ...render(ui, { wrapper: Wrapper, ...options }) }
}
