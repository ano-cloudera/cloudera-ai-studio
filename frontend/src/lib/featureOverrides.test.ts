import { afterEach, describe, expect, it } from 'vitest'
import {
  LOCKED_FEATURES,
  SWITCHABLE_FEATURES,
  featureEnabled,
  featureForPath,
  getFeatureOverrides,
  restoreCachedFeatureOverrides,
  setFeatureOverrides,
  type FeatureKey,
} from './featureOverrides'

const defaults: Record<FeatureKey, boolean> = {
  askData: true, usage: true, settings: true, documents: true, connectors: true, prompts: true, skills: false, semanticLayer: true, aiModelRegistry: true,
}

describe('feature overrides', () => {
  afterEach(() => {
    setFeatureOverrides({}, { cache: false })
    window.localStorage.clear()
  })

  it('keeps the deployment default unless a switchable feature is overridden', () => {
    expect(featureEnabled('skills', defaults)).toBe(false)
    setFeatureOverrides({ skills: true, usage: false })
    expect(featureEnabled('skills', defaults)).toBe(true)
    expect(featureEnabled('usage', defaults)).toBe(false)
    expect(featureEnabled('prompts', defaults)).toBe(true)
  })

  it('never lets a locked feature be switched, even if the data says so', () => {
    setFeatureOverrides({ askData: false, settings: false, aiModelRegistry: false } as never)
    expect(getFeatureOverrides()).toEqual({})
    for (const key of LOCKED_FEATURES) expect(featureEnabled(key, defaults)).toBe(true)
    expect(SWITCHABLE_FEATURES).not.toContain('askData')
    expect(SWITCHABLE_FEATURES).not.toContain('settings')
  })

  it('remembers the last answer for the next visit and ignores junk in the cache', () => {
    setFeatureOverrides({ prompts: false })
    setFeatureOverrides({}, { cache: false }) // a fresh page load starts empty
    restoreCachedFeatureOverrides()
    expect(getFeatureOverrides()).toEqual({ prompts: false })
    window.localStorage.setItem('anywhere.feature-overrides', '{not json')
    expect(() => restoreCachedFeatureOverrides()).not.toThrow()
  })

  it('finds the feature a page belongs to', () => {
    expect(featureForPath('/skills')).toBe('skills')
    expect(featureForPath('/semantic-layer/model')).toBe('semanticLayer')
    expect(featureForPath('/knowledge')).toBe('documents')
    expect(featureForPath('/connectors/abc')).toBe('connectors')
    expect(featureForPath('/')).toBeNull()
    expect(featureForPath('/settings')).toBeNull()
    expect(featureForPath('/skillset')).toBeNull() // only the page and what is under it
  })
})
