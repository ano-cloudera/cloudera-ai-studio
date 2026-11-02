'use client'

import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Reference = { name: string; ref: string; kind: string }

const CUSTOM = '__custom__'
const KIND_ORDER: Record<string, number> = { api_key: 0, password: 1, token: 2, other: 3 }

let cached: Promise<Reference[]> | null = null

/** The variables the Backend can read, loaded once per page. A failed load is retried on the next mount. */
function loadReferences(): Promise<Reference[]> {
  if (!cached) {
    cached = api
      .listEnvironmentReferences()
      .then(res => [...res.references].sort((a, b) => (KIND_ORDER[a.kind] ?? 9) - (KIND_ORDER[b.kind] ?? 9) || a.name.localeCompare(b.name)))
      .catch(error => {
        cached = null
        throw error
      })
  }
  return cached
}

type Props = {
  value: string
  onChange: (value: string) => void
  className?: string
  id?: string
  placeholder?: string
}

/** Pick the environment variable that holds a secret (`env://NAME`), or type another name. Values are never shown. */
export function EnvRefSelect({ value, onChange, className = 'input w-full', id, placeholder = 'env://NAME' }: Props) {
  const [references, setReferences] = useState<Reference[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [typing, setTyping] = useState(false)

  useEffect(() => {
    let alive = true
    loadReferences().then(
      list => alive && setReferences(list),
      () => alive && setFailed(true),
    )
    return () => {
      alive = false
    }
  }, [])

  const loading = references === null && !failed
  const known = references?.some(item => item.ref === value) ?? false
  // Typing is allowed while the list loads, when it cannot be loaded or is empty, and for a name that is not on the list.
  const free = loading || failed || typing || (value.trim() !== '' && !known) || references?.length === 0

  return (
    <div className="space-y-1.5">
      {!failed && references && references.length > 0 ? (
        <select
          id={id}
          className={className}
          value={free ? CUSTOM : value}
          onChange={event => {
            if (event.target.value === CUSTOM) {
              setTyping(true)
              onChange('')
            } else {
              setTyping(false)
              onChange(event.target.value)
            }
          }}
        >
          <option value="">Choose a variable…</option>
          {references.map(item => (
            <option key={item.name} value={item.ref}>
              {item.name}
            </option>
          ))}
          <option value={CUSTOM}>Other (type a name)…</option>
        </select>
      ) : null}
      {free ? (
        <input
          id={references && references.length > 0 ? undefined : id}
          className={`${className} font-mono text-xs`}
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          onChange={event => onChange(event.target.value)}
        />
      ) : null}
      {failed || references?.length === 0 ? (
        <p className="text-xs text-slate-500">
          No credential variables were found on the Backend. Add them in Project Settings, run the Deploy applications Job, then reload this
          page, or type a reference such as {placeholder}.
        </p>
      ) : null}
    </div>
  )
}
