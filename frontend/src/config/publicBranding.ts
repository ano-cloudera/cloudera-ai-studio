/** Server-resolved public branding (hackathon / white-label). Avoids stale NEXT_PUBLIC in client chunks. */

export type PublicBranding = {
  productName: string
  appName: string
  sidebarBrandTitle: string
  sidebarPoweredByLabel: string
  sidebarFooterCaption: string
  headerTitle: string
  logoUrl: string
  emptyStateLogoUrl: string
}

const DEFAULT_PRODUCT = 'Cloudera AI Studio'
const DEFAULT_SHORT = 'AI Studio'

function read(key: string, fallback: string): string {
  const value = process.env[key]?.trim()
  return value || fallback
}

function logoPath(): string {
  return (
    process.env.NEXT_PUBLIC_PRODUCT_LOGO?.trim() ||
    process.env.NEXT_PUBLIC_APP_LOGO?.trim() ||
    '/Logo.png'
  )
}

/** Read at request time in Server Components / layout — same values passed to client via context. */
export function resolvePublicBranding(): PublicBranding {
  const productName = read('NEXT_PUBLIC_PRODUCT_NAME', DEFAULT_PRODUCT)
  const appName = read('NEXT_PUBLIC_APP_NAME', productName)
  const customerName = read('NEXT_PUBLIC_CUSTOMER_NAME', '')
  const logo = logoPath()
  const emptyStateLogo =
    process.env.NEXT_PUBLIC_EMPTY_STATE_LOGO?.trim() ||
    process.env.NEXT_PUBLIC_PRODUCT_LOGO?.trim() ||
    process.env.NEXT_PUBLIC_APP_LOGO?.trim() ||
    logo
  const cacheBust = logo.includes('anywhere') ? '?v=hackathon' : ''
  return {
    productName,
    appName,
    sidebarBrandTitle: customerName || appName,
    sidebarPoweredByLabel: read('NEXT_PUBLIC_SIDEBAR_POWERED_BY', 'Powered by Cloudera'),
    sidebarFooterCaption:
      process.env.NEXT_PUBLIC_SIDEBAR_FOOTER_CAPTION?.trim() || productName,
    headerTitle: [customerName, appName].filter(Boolean).join(' ') || appName,
    logoUrl: `${logo}${cacheBust}`,
    emptyStateLogoUrl: `${emptyStateLogo}${cacheBust}`,
  }
}
