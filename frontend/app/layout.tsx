import type { ReactNode } from 'react'
import { Plus_Jakarta_Sans } from 'next/font/google'
import '../src/index.css'
import { AppShell } from '../src/layout/AppShell'
import { appConfig, PRODUCT_NAME } from '../src/config/appConfig'
import { Providers } from './providers'

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  display: 'swap',
})

export const metadata = {
  title: {
    default: appConfig.productName || PRODUCT_NAME,
    template: `%s | ${PRODUCT_NAME}`,
  },
  description: appConfig.emptyStateDescription,
  icons: {
    icon: [{ url: appConfig.branding.logo, type: 'image/png' }],
    apple: [{ url: appConfig.branding.logo, type: 'image/png' }],
  },
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={plusJakarta.variable}>
      <body className={plusJakarta.className}>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  )
}
