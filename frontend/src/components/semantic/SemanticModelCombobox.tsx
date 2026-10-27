'use client'

import { Search } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { SemanticModelRecord } from '../../types/api'

const MAX_VISIBLE_RESULTS = 50

type Props = {
  models: SemanticModelRecord[]
  value: string
  onChange: (modelId: string) => void
  disabled?: boolean
  'aria-label'?: string
}

export function SemanticModelCombobox({ models, value, onChange, disabled, 'aria-label': ariaLabel }: Props) {
  const listId = useId()
  const inputId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)

  const selected = useMemo(() => models.find(m => m.id === value) ?? null, [models, value])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return models
    return models.filter(m => m.name.toLowerCase().includes(q) || m.key.toLowerCase().includes(q))
  }, [models, query])

  const visibleResults = useMemo(() => {
    const q = query.trim()
    if (!q && value) {
      const selectedModel = models.find(m => m.id === value)
      const rest = models.filter(m => m.id !== value)
      const merged = selectedModel ? [selectedModel, ...rest] : models
      return merged.slice(0, MAX_VISIBLE_RESULTS)
    }
    return filtered.slice(0, MAX_VISIBLE_RESULTS)
  }, [models, filtered, query, value])
  const resultsTruncated = filtered.length > MAX_VISIBLE_RESULTS

  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  useEffect(() => {
    if (!open) {
      setQuery('')
      return
    }
    searchRef.current?.focus()
    const selectedIdx = visibleResults.findIndex(m => m.id === value)
    setActiveIndex(selectedIdx >= 0 ? selectedIdx : 0)
  }, [open, value, visibleResults])

  useEffect(() => {
    setActiveIndex(i => Math.min(i, Math.max(visibleResults.length - 1, 0)))
  }, [query, visibleResults.length])

  function select(id: string) {
    onChange(id)
    setOpen(false)
    setQuery('')
  }

  function openList() {
    if (disabled) return
    setOpen(true)
  }

  return (
    <div ref={rootRef} className="relative min-w-[200px] flex-1" data-testid="semantic-model-combobox">
      <label htmlFor={inputId} className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Semantic model
      </label>
      <button
        type="button"
        id={inputId}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel ?? 'Search semantic models'}
        disabled={disabled}
        data-testid="semantic-model-combobox-trigger"
        className="mt-0.5 flex h-10 w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-left shadow-sm focus:outline-none focus:ring-2 focus:ring-cloudera-orange/25"
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={e => {
          if (e.key === 'ArrowDown' || e.key === 'Enter') {
            e.preventDefault()
            openList()
          }
        }}
      >
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-cloudera-navy">
          {selected ? selected.name : <span className="font-normal text-slate-500">Select semantic model</span>}
        </span>
        <Search className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden />
        <span aria-hidden className="text-xs text-slate-400">
          ▾
        </span>
      </button>
      {open ? (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
          <input
            ref={searchRef}
            type="search"
            data-testid="semantic-model-combobox-search"
            className="w-full border-b border-slate-100 px-3 py-2 text-sm focus:outline-none"
            placeholder="Search semantic models…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Escape') {
                setOpen(false)
                return
              }
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setActiveIndex(i => Math.min(i + 1, Math.max(visibleResults.length - 1, 0)))
              }
              if (e.key === 'ArrowUp') {
                e.preventDefault()
                setActiveIndex(i => Math.max(i - 1, 0))
              }
              if (e.key === 'Enter' && visibleResults[activeIndex]) {
                e.preventDefault()
                select(visibleResults[activeIndex].id)
              }
            }}
          />
          <ul id={listId} role="listbox" data-testid="semantic-model-combobox-list" className="max-h-56 overflow-y-auto py-1 text-sm">
            {visibleResults.map((m, idx) => (
              <li key={m.id} role="option" aria-selected={m.id === value}>
                <button
                  type="button"
                  data-model-id={m.id}
                  className={`flex w-full flex-col px-3 py-1.5 text-left hover:bg-slate-50 ${idx === activeIndex ? 'bg-violet-50' : ''} ${m.id === value ? 'font-semibold text-cloudera-violet' : ''}`}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => select(m.id)}
                >
                  <span className="truncate text-sm">{m.name}</span>
                  <span className="truncate text-[11px] text-slate-500">{m.key}</span>
                </button>
              </li>
            ))}
            {!visibleResults.length ? <li className="px-3 py-2 text-xs text-slate-500">No models match</li> : null}
            {resultsTruncated ? (
              <li className="border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">
                Showing {MAX_VISIBLE_RESULTS} of {filtered.length} — refine search to narrow results
              </li>
            ) : null}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
