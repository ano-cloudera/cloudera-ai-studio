import { describe, expect, it } from 'vitest'

import type { ModelInfo } from '../types/api'
import { pickDefaultSelection } from './modelSelectionSlice'

const qwenEnv: ModelInfo = { provider: 'qwen', id: 'env-qwen', label: 'Qwen Private', available: false, reason: 'Base URL not configured' }
const gemini: ModelInfo = { provider: 'gemini', id: 'gemini-2.5', label: 'Gemini', available: true, reason: null }
const assigned: ModelInfo = { provider: 'qwen', id: 'Qwen3.5-9B', label: 'qwen3.5-9b', available: true, reason: null, assigned: true }

describe('default model selection', () => {
  it('uses the model assigned in Settings -> AI Models, even when the browser saved another one', () => {
    const picked = pickDefaultSelection([assigned, gemini], { provider: 'gemini', model: 'gemini-2.5' })
    expect(picked).toEqual({ provider: 'qwen', model: 'Qwen3.5-9B' })
  })

  it('keeps the saved choice when nothing is assigned, and prefers the private model over Gemini otherwise', () => {
    const openai: ModelInfo = { provider: 'openai', id: 'gpt', label: 'ChatGPT', available: true, reason: null }
    const qwen: ModelInfo = { ...qwenEnv, available: true, reason: null }
    expect(pickDefaultSelection([qwen, gemini, openai], { provider: 'openai', model: 'gpt' })).toEqual({ provider: 'openai', model: 'gpt' })
    expect(pickDefaultSelection([qwen, gemini, openai], null)).toEqual({ provider: 'qwen', model: 'env-qwen' })
    expect(pickDefaultSelection([qwenEnv, gemini], null)).toEqual({ provider: 'gemini', model: 'gemini-2.5' })
  })

  it('selects nothing when no model is available', () => {
    expect(pickDefaultSelection([qwenEnv], null)).toBeNull()
    expect(pickDefaultSelection([], null)).toBeNull()
  })
})
