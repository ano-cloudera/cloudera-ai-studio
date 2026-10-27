'use client'

import type { ReactNode } from 'react'
import { Provider } from 'react-redux'
import { ModelSelectionBootstrap } from '../src/store/ModelSelectionBootstrap'
import { store } from '../src/store/store'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <Provider store={store}>
      <ModelSelectionBootstrap>{children}</ModelSelectionBootstrap>
    </Provider>
  )
}
