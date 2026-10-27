'use client'

import React, { createContext, useCallback, useContext, useMemo, useRef } from 'react'

export type EditorDirtyRegistration = {
  isDirty: () => boolean
  save: () => Promise<void>
  discard: () => void
}

type Ctx = {
  register: (registration: EditorDirtyRegistration | null) => void
  activeRegistration: () => EditorDirtyRegistration | null
  isDirty: () => boolean
}

const EditorDirtyContext = createContext<Ctx | null>(null)

export function EditorDirtyProvider({ children }: { children: React.ReactNode }) {
  const regRef = useRef<EditorDirtyRegistration | null>(null)
  const register = useCallback((registration: EditorDirtyRegistration | null) => {
    regRef.current = registration
  }, [])
  const activeRegistration = useCallback(() => regRef.current, [])
  const isDirty = useCallback(() => regRef.current?.isDirty() ?? false, [])
  const value = useMemo(() => ({ register, activeRegistration, isDirty }), [register, activeRegistration, isDirty])
  return <EditorDirtyContext.Provider value={value}>{children}</EditorDirtyContext.Provider>
}

const noopCtx: Ctx = {
  register: () => undefined,
  activeRegistration: () => null,
  isDirty: () => false,
}

export function useEditorDirtyRegistry() {
  const ctx = useContext(EditorDirtyContext)
  return ctx ?? noopCtx
}

export function useRegisterEditorDirty(registration: EditorDirtyRegistration | null) {
  const { register } = useEditorDirtyRegistry()
  React.useEffect(() => {
    register(registration)
    return () => register(null)
  }, [register, registration])
}
