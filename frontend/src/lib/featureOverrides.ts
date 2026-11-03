'use client'

import { useSyncExternalStore } from 'react'

export type FeatureKey =
  | 'askData'
  | 'usage'
  | 'settings'
  | 'documents'
  | 'connectors'
  | 'prompts'
  | 'skills'
  | 'semanticLayer'
  | 'aiModelRegistry'

/** Features a workspace may switch. Everything else is always on: the core of the app (Ask Data), the places that configure it
 * (Data Sources, Semantic Layer, AI Models), Usage, and Settings itself, which holds these switches. */
export const SWITCHABLE_FEATURES: FeatureKey[] = ['documents', 'prompts', 'skills']
export const LOCKED_FEATURES: FeatureKey[] = ['askData', 'settings', 'aiModelRegistry', 'connectors', 'semanticLayer', 'usage']

export type FeatureOverrides = Partial<Record<FeatureKey, boolean>>

export const FEATURE_LABELS: Record<FeatureKey, string> = {
  askData: 'Ask Data',
  documents: 'Knowledge',
  prompts: 'Prompts',
  skills: 'Skills',
  semanticLayer: 'Semantic Layer',
  connectors: 'Data Sources',
  usage: 'Usage',
  settings: 'Settings',
  aiModelRegistry: 'AI Models',
}

/** What switching a feature off does, shown next to its switch. */
export const FEATURE_NOTES: Partial<Record<FeatureKey, string>> = {
  documents: 'Hides Knowledge and the library choice in the chat. Libraries are kept.',
  prompts: 'Hides Prompts. Published prompts are still used by Ask Data and Knowledge.',
  skills: 'Hides Skills.',
}

/** Why a locked feature has no switch. */
export const LOCKED_NOTES: Partial<Record<FeatureKey, string>> = {
  askData: 'The core of the app.',
  settings: 'Needed to switch anything back on.',
  connectors: 'Ask Data answers from these data sources.',
  semanticLayer: 'Ask Data answers from its published models.',
  usage: 'Always available.',
}

/** Menu and page prefixes, to find which feature a page belongs to. */
const ROUTE_FEATURE: [string, FeatureKey][] = [
  ['/knowledge', 'documents'],
  ['/prompts', 'prompts'],
  ['/skills', 'skills'],
  ['/semantic-layer', 'semanticLayer'],
  ['/connectors', 'connectors'],
  ['/usage', 'usage'],
]

export function featureForPath(pathname: string): FeatureKey | null {
  return ROUTE_FEATURE.find(([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`))?.[1] ?? null
}

let overrides: FeatureOverrides = {}
const listeners = new Set<() => void>()
const CACHE_KEY = 'anywhere.feature-overrides'

function notify() {
  listeners.forEach(listener => listener())
}

export function getFeatureOverrides(): FeatureOverrides {
  return overrides
}

/** Only switchable features can be overridden; anything else in the data is ignored. */
export function setFeatureOverrides(next: FeatureOverrides, { cache = true }: { cache?: boolean } = {}): void {
  const clean: FeatureOverrides = {}
  for (const key of SWITCHABLE_FEATURES) if (typeof next[key] === 'boolean') clean[key] = next[key]
  overrides = clean
  if (cache) {
    try {
      window.localStorage.setItem(CACHE_KEY, JSON.stringify(clean))
    } catch {
      /* a private window or blocked storage: the server copy is still loaded on every start */
    }
  }
  notify()
}

/** The copy from the last visit, applied before the server answers so the menu does not jump. */
export function restoreCachedFeatureOverrides(): void {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY)
    if (raw) setFeatureOverrides(JSON.parse(raw) as FeatureOverrides, { cache: false })
  } catch {
    /* nothing cached, or unreadable */
  }
}

export function subscribeFeatureOverrides(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Re-render when the overrides change. */
export function useFeatureOverrides(): FeatureOverrides {
  return useSyncExternalStore(subscribeFeatureOverrides, getFeatureOverrides, () => ({}))
}

/** The deployment default, unless the workspace switched a switchable feature. */
export function featureEnabled(key: FeatureKey, defaults: Record<FeatureKey, boolean>): boolean {
  if (LOCKED_FEATURES.includes(key)) return defaults[key]
  return overrides[key] ?? defaults[key]
}
