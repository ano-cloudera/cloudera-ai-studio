'use client'

import { useEffect, useMemo, useRef } from 'react'
import { BookOpen, Database, Layers, Plug, Search, Sigma } from 'lucide-react'
import type { ChatContextSource } from '../../lib/chatContext'

export type ContextPickerOption = {
  source: ChatContextSource
  subtitle?: string
  group?: string
}

function optionIcon(type: ChatContextSource['type']) {
  if (type === 'table') return Database
  if (type === 'semantic_metric') return Sigma
  if (type === 'semantic_term') return BookOpen
  if (type === 'semantic_model' || type === 'semantic_entity') return Layers
  if (type === 'mcp_connector') return Plug
  return BookOpen
}

type Props = {
  open: boolean
  query: string
  searchText: string
  onSearchTextChange: (value: string) => void
  options: ContextPickerOption[]
  activeIndex: number
  onHighlight?: (index: number) => void
  onSelect: (source: ChatContextSource) => void
  onClose: () => void
}

export function contextPickerFilterQuery(mentionQuery: string, searchText: string): string {
  const fromSearch = searchText.trim().toLowerCase()
  if (fromSearch) return fromSearch
  return mentionQuery.trim().toLowerCase()
}

export function filterContextPickerOptions(options: ContextPickerOption[], filterQuery: string) {
  if (!filterQuery) return options
    return options.filter(opt => {
      const hay = `${opt.source.name} ${opt.subtitle ?? ''}`.toLowerCase()
      return hay.includes(filterQuery)
    })
}

export function ContextPicker({
  open,
  query,
  searchText,
  onSearchTextChange,
  options,
  activeIndex,
  onHighlight,
  onSelect,
  onClose,
}: Props) {
  const listRef = useRef<HTMLDivElement>(null)

  const filterQuery = useMemo(
    () => contextPickerFilterQuery(query, searchText),
    [query, searchText],
  )

  const filtered = useMemo(
    () => filterContextPickerOptions(options, filterQuery),
    [options, filterQuery],
  )

  useEffect(() => {
    if (open) onHighlight?.(0)
  }, [filterQuery, open, onHighlight])

  useEffect(() => {
    if (!open) return
    function onDocKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onDocKey)
    return () => document.removeEventListener('keydown', onDocKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label="Attach context"
      className="absolute bottom-full left-0 z-20 mb-2 w-full max-w-md overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg"
    >
      <div className="border-b border-slate-100 px-3 py-2">
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Attach context</p>
        <label className="relative mt-2 flex items-center">
          <Search size={15} className="pointer-events-none absolute left-2.5 text-slate-400" aria-hidden />
          <input
            type="search"
            value={searchText}
            onChange={event => onSearchTextChange(event.target.value)}
            onKeyDown={event => {
              event.stopPropagation()
              handleContextPickerKeyDown(
                event,
                filtered.length,
                activeIndex,
                idx => onHighlight?.(typeof idx === 'function' ? idx(activeIndex) : idx),
                index => {
                  const picked = filtered[index]
                  if (picked) onSelect(picked.source)
                },
                onClose,
              )
            }}
            placeholder="Search by name…"
            aria-label="Search knowledge libraries by name"
            data-testid="context-picker-search"
            className="w-full rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-8 pr-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-cloudera-violet/40 focus:bg-white focus:outline-none focus:ring-2 focus:ring-cloudera-violet/20"
          />
        </label>
      </div>
      {filtered.length === 0 ? (
        <p className="px-3 py-4 text-sm text-slate-600">No matching context</p>
      ) : (
        <ul className="max-h-56 overflow-y-auto py-1">
          {filtered.map((opt, index) => {
            const Icon = optionIcon(opt.source.type)
            const prevGroup = index > 0 ? filtered[index - 1]?.group : undefined
            const showGroup = opt.group && opt.group !== prevGroup
            return (
              <li key={`${opt.source.type}-${opt.source.id}`}>
                {showGroup ? (
                  <div className="px-3 pb-1 pt-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">
                    {opt.group}
                  </div>
                ) : null}
                <button
                  type="button"
                  role="option"
                  aria-selected={index === activeIndex}
                  className={`flex w-full items-start gap-2 px-3 py-2 text-left text-sm ${
                    index === activeIndex ? 'bg-cloudera-violet/10 text-cloudera-navy' : 'text-slate-700 hover:bg-slate-50'
                  }`}
                  onMouseEnter={() => onHighlight?.(index)}
                  onClick={() => onSelect(opt.source)}
                >
                  <Icon size={16} className="mt-0.5 shrink-0 text-cloudera-violet" aria-hidden />
                  <span>
                    <span className="block font-semibold">{opt.source.name}</span>
                    {opt.subtitle ? <span className="block text-xs text-slate-500">{opt.subtitle}</span> : null}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export function handleContextPickerKeyDown(
  event: React.KeyboardEvent,
  filteredCount: number,
  activeIndex: number,
  setActiveIndex: (value: number | ((prev: number) => number)) => void,
  onSelectIndex: (index: number) => void,
  onClose: () => void,
): boolean {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (filteredCount) setActiveIndex(i => (i + 1) % filteredCount)
    return true
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (filteredCount) setActiveIndex(i => (i - 1 + filteredCount) % filteredCount)
    return true
  }
  if (event.key === 'Enter' && filteredCount) {
    event.preventDefault()
    onSelectIndex(activeIndex)
    return true
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    onClose()
    return true
  }
  return false
}
