'use client'

import { useEffect, type ReactNode } from 'react'
import { useAppDispatch } from './hooks'
import { fetchModels } from './modelSelectionSlice'

export function ModelSelectionBootstrap({ children }: { children: ReactNode }) {
  const dispatch = useAppDispatch()
  useEffect(() => {
    void dispatch(fetchModels())
  }, [dispatch])
  return <>{children}</>
}
