'use client'

import type { ReactNode } from 'react'
import { useCallback } from 'react'
import { useAppDispatch, useAppSelector } from '../store/hooks'
import { fetchModels, setSelection } from '../store/modelSelectionSlice'
import type { ModelInfo, ModelSelection } from '../types/api'

/** @deprecated Redux Provider at root loads models; wrapper kept for test compatibility. */
export function ModelSelectionProvider({ children }: { children: ReactNode }) {
  return <>{children}</>
}

export function useModelSelection(): {
  models: ModelInfo[]
  selection: ModelSelection | null
  loading: boolean
  loadedOnce: boolean
  error: string
  select: (selection: ModelSelection) => void
  retryLoad: () => void
} {
  const dispatch = useAppDispatch()
  const models = useAppSelector(state => state.modelSelection.models)
  const selection = useAppSelector(state => state.modelSelection.selection)
  const loading = useAppSelector(state => state.modelSelection.loading)
  const loadedOnce = useAppSelector(state => state.modelSelection.loadedOnce)
  const error = useAppSelector(state => state.modelSelection.error)
  const select = useCallback(
    (next: ModelSelection) => {
      dispatch(setSelection(next))
    },
    [dispatch],
  )
  const retryLoad = useCallback(() => {
    void dispatch(fetchModels())
  }, [dispatch])
  return { models, selection, loading, loadedOnce, error, select, retryLoad }
}
