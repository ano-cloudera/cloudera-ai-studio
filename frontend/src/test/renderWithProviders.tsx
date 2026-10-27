import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { Provider } from 'react-redux'
import { ModelSelectionBootstrap } from '../store/ModelSelectionBootstrap'
import { createAppStore } from '../store/store'

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  const store = createAppStore()
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <ModelSelectionBootstrap>{children}</ModelSelectionBootstrap>
      </Provider>
    )
  }
  return { store, ...render(ui, { wrapper: Wrapper, ...options }) }
}
