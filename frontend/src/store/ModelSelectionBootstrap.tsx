'use client'

import { useEffect, type ReactNode } from 'react'
import { useAppDispatch } from './hooks'
import { fetchModels, hydrateSavedSelection } from './modelSelectionSlice'

export function ModelSelectionBootstrap({ children }: { children: ReactNode }) {
  const dispatch = useAppDispatch()
  useEffect(() => {
    dispatch(hydrateSavedSelection())
    void dispatch(fetchModels())
  }, [dispatch])
  return <>{children}</>
}
