'use client'

import { useMemo, useState } from 'react'

export type GlossaryRelatedOption = { key: string; label: string; kind: 'entity' | 'metric' | 'dimension' }

type Props = {
  options: GlossaryRelatedOption[]
  selectedEntityKeys: string[]
  selectedMetricKeys: string[]
  selectedDimensionKeys: string[]
  onChange: (next: { entityKeys: string[]; metricKeys: string[]; dimensionKeys: string[] }) => void
}

const KIND_LABEL: Record<GlossaryRelatedOption['kind'], string> = {
  entity: 'Data Models',
  metric: 'Metrics',
  dimension: 'Dimensions',
}

function toggleKey(list: string[], key: string): string[] {
  return list.includes(key) ? list.filter(k => k !== key) : [...list, key]
}

export function GlossaryRelatedObjectPicker({
  options,
  selectedEntityKeys,
  selectedMetricKeys,
  selectedDimensionKeys,
  onChange,
}: Props) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter(o => o.label.toLowerCase().includes(q) || o.key.toLowerCase().includes(q))
  }, [options, query])

  const grouped = useMemo(() => {
    const buckets: Record<GlossaryRelatedOption['kind'], GlossaryRelatedOption[]> = {
      entity: [],
      metric: [],
      dimension: [],
    }
    for (const o of filtered) buckets[o.kind].push(o)
    return buckets
  }, [filtered])

  const selectedChips = useMemo(() => {
    const byKey = new Map(options.map(o => [o.key, o]))
    const keys = [
      ...selectedEntityKeys.map(k => ({ kind: 'entity' as const, key: k })),
      ...selectedMetricKeys.map(k => ({ kind: 'metric' as const, key: k })),
      ...selectedDimensionKeys.map(k => ({ kind: 'dimension' as const, key: k })),
    ]
    return keys.map(({ kind, key }) => {
      const opt = byKey.get(key)
      return { kind, key, label: opt?.label ?? key }
    })
  }, [options, selectedEntityKeys, selectedMetricKeys, selectedDimensionKeys])

  function isSelected(kind: GlossaryRelatedOption['kind'], key: string): boolean {
    if (kind === 'entity') return selectedEntityKeys.includes(key)
    if (kind === 'metric') return selectedMetricKeys.includes(key)
    return selectedDimensionKeys.includes(key)
  }

  function toggle(kind: GlossaryRelatedOption['kind'], key: string) {
    if (kind === 'entity') {
      onChange({
        entityKeys: toggleKey(selectedEntityKeys, key),
        metricKeys: selectedMetricKeys,
        dimensionKeys: selectedDimensionKeys,
      })
    } else if (kind === 'metric') {
      onChange({
        entityKeys: selectedEntityKeys,
        metricKeys: toggleKey(selectedMetricKeys, key),
        dimensionKeys: selectedDimensionKeys,
      })
    } else {
      onChange({
        entityKeys: selectedEntityKeys,
        metricKeys: selectedMetricKeys,
        dimensionKeys: toggleKey(selectedDimensionKeys, key),
      })
    }
  }

  function removeChip(kind: GlossaryRelatedOption['kind'], key: string) {
    toggle(kind, key)
  }

  return (
    <div className="grid gap-2">
      <span className="text-xs font-semibold text-slate-600">Related objects</span>
      <div className="flex flex-wrap gap-1">
        {selectedChips.length === 0 ? (
          <span className="text-xs text-slate-500">None selected</span>
        ) : (
          selectedChips.map(chip => (
            <span
              key={`${chip.kind}-${chip.key}`}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-800"
            >
              {KIND_LABEL[chip.kind].replace(/s$/, '')}: {chip.label}
              <button
                type="button"
                className="text-slate-500 hover:text-red-600"
                aria-label={`Remove ${chip.label}`}
                onClick={() => removeChip(chip.kind, chip.key)}
              >
                ×
              </button>
            </span>
          ))
        )}
      </div>
      <input
        type="search"
        className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
        placeholder="Search data models, metrics, dimensions…"
        value={query}
        onChange={e => setQuery(e.target.value)}
      />
      <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 p-2 text-sm">
        {(['entity', 'metric', 'dimension'] as const).map(kind =>
          grouped[kind].length ? (
            <div key={kind} className="mb-2">
              <p className="text-xs font-semibold uppercase text-slate-500">{KIND_LABEL[kind]}</p>
              <ul className="mt-1 space-y-1">
                {grouped[kind].map(opt => (
                  <li key={`${kind}-${opt.key}`}>
                    <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 hover:bg-slate-50">
                      <input
                        type="checkbox"
                        checked={isSelected(kind, opt.key)}
                        onChange={() => toggle(kind, opt.key)}
                      />
                      <span>{opt.label}</span>
                      <span className="font-mono text-xs text-slate-400">{opt.key}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          ) : null,
        )}
        {!filtered.length ? <p className="text-xs text-slate-500">No matches</p> : null}
      </div>
    </div>
  )
}
