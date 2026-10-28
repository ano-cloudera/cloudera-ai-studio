'use client'

import type { ReactNode } from 'react'
import { Provider } from 'react-redux'
import type { PublicBranding } from '../src/config/publicBranding'
import { PublicBrandingProvider } from '../src/config/PublicBrandingContext'
import { ModelSelectionBootstrap } from '../src/store/ModelSelectionBootstrap'
import { store } from '../src/store/store'

export function Providers({
  branding,
  children,
}: {
  branding: PublicBranding
  children: ReactNode
}) {
  return (
    <Provider store={store}>
      <PublicBrandingProvider branding={branding}>
        <ModelSelectionBootstrap>{children}</ModelSelectionBootstrap>
      </PublicBrandingProvider>
    </Provider>
  )
}
