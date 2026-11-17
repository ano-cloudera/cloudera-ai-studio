/** Server-resolved public branding (hackathon / white-label). Avoids stale NEXT_PUBLIC in client chunks. */

export type PublicBranding = {
  productName: string
  appName: string
  sidebarBrandTitle: string
  sidebarPoweredByLabel: string
  sidebarFooterCaption: string
  /** The mark beside "Powered by ..." in the sidebar footer: the platform's, not the product's own logo. */
  sidebarPoweredByLogoUrl: string
  headerTitle: string
  /** A longer line beside the header title (what the name stands for); empty when it only repeats the name. */
  headerTagline?: string
  logoUrl: string
  emptyStateLogoUrl: string
}

const DEFAULT_PRODUCT = 'Anywhere AI Studio'
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

/** The tagline, unless it only repeats the product name (the default), so the stock header stays as it is. */
function headerTagline(productName: string, appName: string): string {
  const tagline = process.env.NEXT_PUBLIC_APP_TAGLINE?.trim() ?? ''
  const same = [productName, appName, DEFAULT_PRODUCT, DEFAULT_SHORT].some(name => name.trim().toLowerCase() === tagline.toLowerCase())
  return tagline && !same ? tagline : ''
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
    // A second line under "Powered by" only when one is set; the product name is already in the header.
    sidebarFooterCaption: process.env.NEXT_PUBLIC_SIDEBAR_FOOTER_CAPTION?.trim() || '',
    sidebarPoweredByLogoUrl: process.env.NEXT_PUBLIC_SIDEBAR_POWERED_BY_LOGO?.trim() || '/cloudera-logo.png',
    headerTitle: [customerName, appName].filter(Boolean).join(' ') || appName,
    headerTagline: headerTagline(productName, appName),
    logoUrl: `${logo}${cacheBust}`,
    emptyStateLogoUrl: `${emptyStateLogo}${cacheBust}`,
  }
}
