'use client'

import { createContext, useContext, type ReactNode } from 'react'
import type { PublicBranding } from './publicBranding'

const PublicBrandingContext = createContext<PublicBranding | null>(null)

export function PublicBrandingProvider({
  branding,
  children,
}: {
  branding: PublicBranding
  children: ReactNode
}) {
  return <PublicBrandingContext.Provider value={branding}>{children}</PublicBrandingContext.Provider>
}

export function usePublicBranding(): PublicBranding {
  const ctx = useContext(PublicBrandingContext)
  if (!ctx) {
    throw new Error('usePublicBranding requires PublicBrandingProvider')
  }
  return ctx
}
