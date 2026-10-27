'use client'

import { useCallback, useEffect, useState } from 'react'
import { Layers } from 'lucide-react'
import { api } from '../../lib/api'

type Props = {
  onPickQuestion: (text: string) => void
}

export function AskDataSemanticCatalogPanel({ onPickQuestion }: Props) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [modelName, setModelName] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<{ name: string; key: string; description?: string }[]>([])
  const [dimensions, setDimensions] = useState<{ name: string; key: string; description?: string }[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.getAskDataSemanticCatalog()
      setModelName(res.model?.name ?? null)
      setMetrics(res.metrics ?? [])
      setDimensions(res.dimensions ?? [])
    } catch {
      setModelName(null)
      setMetrics([])
      setDimensions([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  if (!open && !modelName && metrics.length === 0) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mb-2 flex items-center gap-2 text-xs font-semibold text-cloudera-navy/80 hover:text-cloudera-navy"
      >
        <Layers size={14} aria-hidden />
        Browse published metrics
      </button>
    )
  }

  return (
    <div className="mb-3 rounded-xl border border-slate-200/90 bg-white/80 px-3 py-2">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left text-xs font-semibold text-cloudera-navy"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <Layers size={14} className="text-cloudera-orange" aria-hidden />
        {modelName ? `Ontology: ${modelName}` : 'Published semantic catalog'}
        <span className="ml-auto text-slate-400">{open ? '▾' : '▸'}</span>
      </button>
      {open ? (
        <div className="mt-2 max-h-48 space-y-2 overflow-y-auto text-xs text-slate-700">
          {loading ? <p className="text-slate-500">Loading…</p> : null}
          {!loading && metrics.length === 0 && dimensions.length === 0 ? (
            <p className="text-slate-500">Publish a semantic model to browse metrics here.</p>
          ) : null}
          {metrics.length > 0 ? (
            <div>
              <p className="font-semibold text-slate-600">Metrics</p>
              <ul className="mt-1 space-y-1">
                {metrics.map(m => (
                  <li key={m.key}>
                    <button
                      type="button"
                      className="text-left hover:text-cloudera-orange"
                      onClick={() => onPickQuestion(`What is ${m.name}?`)}
                    >
                      {m.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {dimensions.length > 0 ? (
            <div>
              <p className="font-semibold text-slate-600">Dimensions</p>
              <ul className="mt-1 space-y-1">
                {dimensions.slice(0, 12).map(d => (
                  <li key={d.key}>{d.name}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
