import type { ReactNode } from 'react'
import { PublicBrandingProvider } from '../config/PublicBrandingContext'
import { resolvePublicBranding } from '../config/publicBranding'

const testBranding = resolvePublicBranding()

export function TestBrandingWrapper({ children }: { children: ReactNode }) {
  return <PublicBrandingProvider branding={testBranding}>{children}</PublicBrandingProvider>
}
