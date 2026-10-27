import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { api } from '../lib/api'
import type { ModelInfo, ModelSelection } from '../types/api'

const STORAGE_KEY = 'accelerator.model-selection'

export type ModelSelectionState = {
  models: ModelInfo[]
  selection: ModelSelection | null
  loading: boolean
  loadedOnce: boolean
  error: string
}

const initialState: ModelSelectionState = {
  models: [],
  selection: null,
  loading: false,
  loadedOnce: false,
  error: '',
}

function readSavedSelection(): ModelSelection | null {
  if (typeof window === 'undefined') return null
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') as ModelSelection | null
  } catch {
    return null
  }
}

function pickDefaultSelection(models: ModelInfo[], saved: ModelSelection | null): ModelSelection | null {
  const available = models.filter(model => model.available)
  const selected =
    available.find(model => model.provider === saved?.provider && model.id === saved?.model)
    || available.find(model => model.provider === 'gemini')
    || available[0]
  return selected ? { provider: selected.provider, model: selected.id } : null
}

export const fetchModels = createAsyncThunk('modelSelection/fetchModels', async () => {
  const { models } = await api.models()
  return models
})

const modelSelectionSlice = createSlice({
  name: 'modelSelection',
  initialState,
  reducers: {
    setSelection(state, action: PayloadAction<ModelSelection>) {
      const allowed = state.models.some(
        model => model.available && model.provider === action.payload.provider && model.id === action.payload.model,
      )
      if (!allowed) return
      state.selection = action.payload
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(action.payload))
      } catch {
        /* optional persistence */
      }
    },
  },
  extraReducers: builder => {
    builder
      .addCase(fetchModels.pending, state => {
        state.loading = true
        state.error = ''
      })
      .addCase(fetchModels.fulfilled, (state, action) => {
        state.loading = false
        state.loadedOnce = true
        state.models = action.payload
        state.selection = pickDefaultSelection(action.payload, readSavedSelection())
      })
      .addCase(fetchModels.rejected, (state, action) => {
        state.loading = false
        if (action.meta.aborted) {
          return
        }
        state.loadedOnce = true
        state.error = 'Unable to load available models.'
      })
  },
})

export const { setSelection } = modelSelectionSlice.actions
export default modelSelectionSlice.reducer
