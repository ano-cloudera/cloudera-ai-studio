import type { ReactNode } from 'react'
import { Plus_Jakarta_Sans } from 'next/font/google'
import '../src/index.css'
import { AppShell } from '../src/layout/AppShell'
import { appConfig, PRODUCT_NAME } from '../src/config/appConfig'
import { resolvePublicBranding } from '../src/config/publicBranding'
import { Providers } from './providers'

const publicBranding = resolvePublicBranding()

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  display: 'swap',
})

const documentTitle = publicBranding.productName || appConfig.productName || PRODUCT_NAME

export const metadata = {
  title: {
    default: documentTitle,
    template: `%s | ${documentTitle}`,
  },
  description: appConfig.emptyStateDescription,
  icons: {
    icon: [{ url: publicBranding.logoUrl, type: 'image/png' }],
    apple: [{ url: publicBranding.logoUrl, type: 'image/png' }],
  },
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={plusJakarta.variable}>
      <body className={plusJakarta.className}>
        <Providers branding={publicBranding}>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  )
}
