import { configureStore } from '@reduxjs/toolkit'
import modelSelectionReducer from './modelSelectionSlice'

export function createAppStore() {
  return configureStore({
    reducer: {
      modelSelection: modelSelectionReducer,
    },
  })
}

export const store = createAppStore()

export type AppStore = ReturnType<typeof createAppStore>
export type RootState = ReturnType<AppStore['getState']>
export type AppDispatch = AppStore['dispatch']
