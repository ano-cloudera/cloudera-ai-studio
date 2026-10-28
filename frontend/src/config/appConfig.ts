/**
 * Canonical product branding (override via NEXT_PUBLIC_* for white-label / hackathon layers).
 * Repository and backend identity remain Cloudera AI Studio — see docs/deployment/HACKATHON_TEMP_BRANDING.md.
 */
export const PRODUCT_NAME = 'Cloudera AI Studio'
export const PRODUCT_SHORT_NAME = 'AI Studio'

/** Branding and copy — override via NEXT_PUBLIC_* env vars for reuse across deployments. */
function env(key: string, fallback: string): string {
  const value = process.env[key]?.trim()
  return value || fallback
}

function envBool(key: string, fallback: boolean): boolean {
  const value = process.env[key]?.trim().toLowerCase()
  if (value === 'true' || value === '1') return true
  if (value === 'false' || value === '0') return false
  return fallback
}

export const appConfig = {
  productName: env('NEXT_PUBLIC_PRODUCT_NAME', PRODUCT_NAME),
  productShortName: env('NEXT_PUBLIC_PRODUCT_SHORT_NAME', PRODUCT_SHORT_NAME),
  appName: env('NEXT_PUBLIC_APP_NAME', PRODUCT_NAME),
  appSubtitle: env('NEXT_PUBLIC_APP_SUBTITLE', PRODUCT_SHORT_NAME),
  projectName: env('NEXT_PUBLIC_PROJECT_NAME', 'Demo Project'),
  customerName: env('NEXT_PUBLIC_CUSTOMER_NAME', ''),
  assistantName: env('NEXT_PUBLIC_ASSISTANT_NAME', 'Assistant'),
  get headerTitle(): string {
    return [this.customerName, this.appName].filter(Boolean).join(' ') || this.appName
  },
  /** Primary line in sidebar header (logo row). */
  get sidebarBrandTitle(): string {
    return this.customerName || this.appName
  },
  get sidebarTagline(): string {
    return env('NEXT_PUBLIC_APP_TAGLINE', this.appSubtitle)
  },
  sidebarPoweredByLabel: env('NEXT_PUBLIC_SIDEBAR_POWERED_BY', 'Powered by Cloudera'),
  get sidebarFooterCaption(): string {
    const explicit = process.env.NEXT_PUBLIC_SIDEBAR_FOOTER_CAPTION?.trim()
    if (explicit) return explicit
    return this.productName
  },
  features: {
    askData: envBool('NEXT_PUBLIC_FEATURE_ASK_DATA', true),
    usage: envBool('NEXT_PUBLIC_FEATURE_USAGE', true),
    settings: envBool('NEXT_PUBLIC_FEATURE_SETTINGS', true),
    documents: envBool('NEXT_PUBLIC_FEATURE_DOCUMENTS', true),
    connectors: envBool('NEXT_PUBLIC_FEATURE_CONNECTORS', true),
    prompts: envBool('NEXT_PUBLIC_FEATURE_PROMPTS', true),
    skills: envBool('NEXT_PUBLIC_FEATURE_SKILLS', true),
    semanticLayer: envBool('NEXT_PUBLIC_FEATURE_SEMANTIC_LAYER', true),
    aiModelRegistry: envBool('NEXT_PUBLIC_FEATURE_AI_MODEL_REGISTRY', true),
  },
  starterQuestionsCaption: env('NEXT_PUBLIC_STARTER_QUESTIONS_CAPTION', 'Start with a question'),
  chatPlaceholder: env('NEXT_PUBLIC_CHAT_PLACEHOLDER', 'Ask a question about your data…'),
  emptyStateTitle: env('NEXT_PUBLIC_EMPTY_STATE_TITLE', 'Ask your data a question'),
  emptyStateDescription: env(
    'NEXT_PUBLIC_EMPTY_STATE_DESCRIPTION',
    'Get a grounded answer, governed metrics, and a relevant visualization.',
  ),
  settingsSubtitle: 'Choose the AI model used for new conversations.',
  settingsModelHelper: 'Select the model you want this assistant to use.',
  navigationAskData: env('NEXT_PUBLIC_NAV_ASK_DATA', 'Ask Data'),
  navigationUsage: env('NEXT_PUBLIC_NAV_USAGE', 'Usage'),
  navigationSettings: env('NEXT_PUBLIC_NAV_SETTINGS', 'Settings'),
  navigationKnowledge: env('NEXT_PUBLIC_NAV_KNOWLEDGE', 'Knowledge'),
  navigationPrompts: env('NEXT_PUBLIC_NAV_PROMPTS', 'Prompts'),
  navigationSkills: env('NEXT_PUBLIC_NAV_SKILLS', 'Skills'),
  navigationSemanticLayer: env('NEXT_PUBLIC_NAV_SEMANTIC_LAYER', 'Semantic Layer'),
  navigationConnectors: env('NEXT_PUBLIC_NAV_CONNECTORS', 'Data Sources'),
  branding: {
    /** Served from `public/` — `NEXT_PUBLIC_PRODUCT_LOGO` alias for hackathon / white-label. */
    logo: env('NEXT_PUBLIC_PRODUCT_LOGO', env('NEXT_PUBLIC_APP_LOGO', '/Logo.png')),
    emptyStateLogo: env(
      'NEXT_PUBLIC_EMPTY_STATE_LOGO',
      env('NEXT_PUBLIC_PRODUCT_LOGO', env('NEXT_PUBLIC_APP_LOGO', '/Logo.png')),
    ),
  },
  /** Genie-style split report panel (frontend-dev). */
  analysisReportPanel: env('NEXT_PUBLIC_ANALYSIS_REPORT_PANEL', 'true') !== 'false',
  reportDocumentLabel: env('NEXT_PUBLIC_REPORT_DOCUMENT_LABEL', 'Analysis Workspace'),
  reportWorkspaceSubtitle: env(
    'NEXT_PUBLIC_REPORT_WORKSPACE_SUBTITLE',
    'Analisis dari percakapan ini',
  ),
  reportDatabaseStatusLabel: env('NEXT_PUBLIC_REPORT_DB_STATUS', 'Platform Ready'),
  platformStatusLabel: env('NEXT_PUBLIC_PLATFORM_STATUS_LABEL', 'Platform Ready'),
  /** When set, Query tab shows “View lineage” linking with `?table=` source. */
  viewLineageBaseUrl: env('NEXT_PUBLIC_LINEAGE_VIEW_URL', ''),
} as const
