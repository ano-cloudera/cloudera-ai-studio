'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ConnectorRecord } from '../../types/api'
import { api } from '../../lib/api'
import { isAppApiError } from '../../lib/apiError'

type Props = {
  open: boolean
  connectors: ConnectorRecord[]
  onClose: () => void
  onCreated: (modelId: string) => void
}

type SelectedTable = {
  connectionId: string
  connectorName: string
  qualified: string
  schema?: string | null
  tableName: string
  catalog?: string | null
}

type SuggestionItem = Record<string, unknown> & {
  suggestion_id?: string
  key?: string
  status?: string
}

type SuggestionBucket = {
  entities?: SuggestionItem[]
  metrics?: SuggestionItem[]
  dimensions?: SuggestionItem[]
  relationships?: SuggestionItem[]
  glossary_suggestions?: SuggestionItem[]
  terms?: SuggestionItem[]
}

type SuggestionDecision = {
  suggestion_id: string
  type: string
  accepted: boolean
  payload: SuggestionItem
  edits: Record<string, string>
  editing: boolean
}

const SECTIONS: Array<{ key: keyof SuggestionBucket; label: string; type: string }> = [
  { key: 'entities', label: 'Data Models', type: 'entity' },
  { key: 'metrics', label: 'Metrics', type: 'metric' },
  { key: 'dimensions', label: 'Dimensions', type: 'dimension' },
  { key: 'relationships', label: 'Relationships', type: 'relationship' },
  { key: 'glossary_suggestions', label: 'Glossary', type: 'term' },
]

function slugKey(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, '_').slice(0, 64)
}

function parseQualified(qualified: string): { catalog: string | null; schema: string | null; tableName: string } {
  const parts = qualified.split('.')
  if (parts.length >= 3) return { catalog: parts[0], schema: parts[1], tableName: parts[2] }
  if (parts.length === 2) return { catalog: null, schema: parts[0], tableName: parts[1] }
  return { catalog: null, schema: null, tableName: parts[0] }
}

const MAX_WIZARD_TABLES = 500

export function CreateSemanticModelWizard({ open, connectors, onClose, onCreated }: Props) {
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [tableSearch, setTableSearch] = useState('')
  const [tablesByConnector, setTablesByConnector] = useState<Record<string, Array<{ name: string; schema?: string | null }>>>({})
  const [tablesLoadState, setTablesLoadState] = useState<Record<string, 'idle' | 'loading' | 'done' | 'error'>>({})
  const [loadingConnector, setLoadingConnector] = useState<string | null>(null)
  const tablesLoadingRef = useRef<Set<string>>(new Set())
  const tablesLoadedRef = useRef<Set<string>>(new Set())
  const [selectedTables, setSelectedTables] = useState<SelectedTable[]>([])
  const [suggestions, setSuggestions] = useState<SuggestionBucket | null>(null)
  const [decisions, setDecisions] = useState<Record<string, SuggestionDecision>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [completion, setCompletion] = useState<{ modelId: string; counts: Record<string, number> } | null>(null)

  const primaryConnectionId = selectedTables[0]?.connectionId ?? connectors[0]?.id ?? ''

  const filteredConnectors = useMemo(() => {
    const q = tableSearch.trim().toLowerCase()
    return connectors.map(c => {
      const rows = tablesByConnector[c.id] ?? []
      const filtered = q
        ? rows.filter(t => {
            const label = [t.schema, t.name].filter(Boolean).join('.').toLowerCase()
            return label.includes(q) || c.name.toLowerCase().includes(q)
          })
        : rows
      return { connector: c, tables: filtered }
    })
  }, [connectors, tablesByConnector, tableSearch])

  const loadConnectorTables = useCallback(async (cid: string, refresh = false) => {
    if (tablesLoadingRef.current.has(cid)) return
    if (!refresh && tablesLoadedRef.current.has(cid)) return

    tablesLoadingRef.current.add(cid)
    setLoadingConnector(cid)
    setTablesLoadState(prev => ({ ...prev, [cid]: 'loading' }))
    setError('')
    try {
      const schemaRes = await api.listConnectorSchemas(cid, { limit: 500 })
      const schemaNames = schemaRes.schemas?.map(s => s.name).filter(Boolean) ?? []
      const merged: Array<{ name: string; schema?: string | null }> = []
      const schemasToQuery = schemaNames.length ? schemaNames : [null]

      for (const schema of schemasToQuery) {
        if (merged.length >= MAX_WIZARD_TABLES) break
        const res = await api.listConnectorTables(cid, {
          schema: schema ?? undefined,
          limit: MAX_WIZARD_TABLES,
        })
        for (const t of res.tables ?? []) {
          merged.push(t)
          if (merged.length >= MAX_WIZARD_TABLES) break
        }
      }

      setTablesByConnector(prev => ({ ...prev, [cid]: merged }))
      tablesLoadedRef.current.add(cid)
      setTablesLoadState(prev => ({ ...prev, [cid]: 'done' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load tables')
      setTablesLoadState(prev => ({ ...prev, [cid]: 'error' }))
    } finally {
      tablesLoadingRef.current.delete(cid)
      setLoadingConnector(null)
    }
  }, [])

  useEffect(() => {
    // The wizard stays mounted while closed; without a reset a finished run reopens on its completion step.
    if (open) return
    setStep(1)
    setName('')
    setDescription('')
    setTableSearch('')
    setSelectedTables([])
    setSuggestions(null)
    setDecisions({})
    setBusy(false)
    setError('')
    setCompletion(null)
  }, [open])

  useEffect(() => {
    if (!open || step !== 2) return
    for (const c of connectors) {
      void loadConnectorTables(c.id)
    }
  }, [open, step, connectors, loadConnectorTables])

  if (!open) return null

  function toggleTable(connector: ConnectorRecord, qualified: string) {
    setSelectedTables(prev => {
      const exists = prev.some(t => t.qualified === qualified && t.connectionId === connector.id)
      if (exists) return prev.filter(t => !(t.qualified === qualified && t.connectionId === connector.id))
      const parsed = parseQualified(qualified)
      return [
        ...prev,
        {
          connectionId: connector.id,
          connectorName: connector.name,
          qualified,
          schema: parsed.schema,
          tableName: parsed.tableName,
          catalog: parsed.catalog,
        },
      ]
    })
  }

  function initDecisions(bucket: SuggestionBucket) {
    const next: Record<string, SuggestionDecision> = {}
    for (const section of SECTIONS) {
      const items = (bucket[section.key] as SuggestionItem[] | undefined) ?? []
      for (const item of items) {
        const sid = String(item.suggestion_id ?? `${section.type}:${item.key ?? ''}`)
        next[sid] = {
          suggestion_id: sid,
          type: section.type,
          accepted: true,
          payload: item,
          edits: {},
          editing: false,
        }
      }
    }
    setDecisions(next)
  }

  async function loadSuggestions() {
    if (!primaryConnectionId || !selectedTables.length) return
    setBusy(true)
    setError('')
    try {
      const res = await api.semanticSuggestions({
        connection_id: primaryConnectionId,
        tables: selectedTables.map(t => t.qualified),
      })
      const bucket = res as SuggestionBucket
      setSuggestions(bucket)
      initDecisions(bucket)
      setStep(3)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Suggestions unavailable')
      setSuggestions(null)
      setDecisions({})
      setStep(3)
    } finally {
      setBusy(false)
    }
  }

  function setDecision(sid: string, patch: Partial<SuggestionDecision>) {
    setDecisions(prev => ({ ...prev, [sid]: { ...prev[sid], ...patch } }))
  }

  function acceptAll() {
    setDecisions(prev => Object.fromEntries(Object.entries(prev).map(([k, d]) => [k, { ...d, accepted: true }])))
  }

  function rejectAll() {
    setDecisions(prev => Object.fromEntries(Object.entries(prev).map(([k, d]) => [k, { ...d, accepted: false }])))
  }

  async function finishCreate() {
    setBusy(true)
    setError('')
    try {
      const key = slugKey(name)
      const { model } = await api.createSemanticModel({ name: name.trim(), key, description: description.trim() || undefined })
      const bootstrap_tables = selectedTables.map(t => {
        const parsed = parseQualified(t.qualified)
        return {
          connection_id: t.connectionId,
          key: slugKey(parsed.tableName),
          name: parsed.tableName.replace(/_/g, ' '),
          description: `Imported from ${t.qualified}`,
          catalog: parsed.catalog ?? undefined,
          schema: parsed.schema ?? undefined,
          table_name: parsed.tableName,
        }
      })
      const selections = Object.values(decisions).map(d => ({
        suggestion_id: d.suggestion_id,
        type: d.type,
        accepted: d.accepted,
        payload: { ...d.payload, ...d.edits },
        changes: d.edits,
      }))
      const accept = await api.acceptSemanticSuggestions(model.id, { bootstrap_tables, selections })
      setCompletion({ modelId: model.id, counts: accept.counts ?? {} })
      setStep(4)
    } catch (err) {
      if (isAppApiError(err) && err.status === 409) {
        setError('A semantic model with this name or key already exists.')
      } else {
        setError(err instanceof Error ? err.message : 'Create failed')
      }
    } finally {
      setBusy(false)
    }
  }

  function labelFor(item: SuggestionItem): string {
    return String(item.name ?? item.term ?? item.key ?? 'Suggestion')
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-label="Create semantic model">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl" data-testid="semantic-create-wizard">
        <h2 className="text-lg font-semibold text-cloudera-navy">Create semantic model</h2>
        <p className="text-xs text-slate-500">Step {Math.min(step, 3)} of 3</p>
        {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}

        {step === 1 ? (
          <div className="mt-4 space-y-3">
            <label className="block text-sm">
              <span className="text-xs font-semibold text-slate-600">Model name</span>
              <input
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Commercial Sales"
              />
            </label>
            <label className="block text-sm">
              <span className="text-xs font-semibold text-slate-600">Description (optional)</span>
              <textarea className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" value={description} onChange={e => setDescription(e.target.value)} rows={2} />
            </label>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="mt-4 space-y-3">
            <input
              type="search"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="Search tables…"
              value={tableSearch}
              onChange={e => setTableSearch(e.target.value)}
            />
            <p className="text-xs text-slate-600">{selectedTables.length} table(s) selected</p>
            <div className="max-h-72 space-y-3 overflow-y-auto">
              {filteredConnectors.map(({ connector, tables }) => {
                const loadState = tablesLoadState[connector.id] ?? 'idle'
                const isLoading = loadingConnector === connector.id || loadState === 'loading'
                return (
                <section key={connector.id} className="rounded-lg border border-slate-100 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-cloudera-navy">{connector.name}</span>
                    <button
                      type="button"
                      data-testid={`semantic-wizard-load-tables-${connector.id}`}
                      className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      disabled={isLoading}
                      onClick={() => void loadConnectorTables(connector.id, true)}
                    >
                      {isLoading ? 'Loading tables…' : loadState === 'done' ? 'Refresh tables' : 'Load tables'}
                    </button>
                  </div>
                  {loadState === 'done' && !tables.length && !isLoading ? (
                    <p className="mt-2 text-xs text-amber-800">No tables found in any schema. Check the data source connection.</p>
                  ) : null}
                  {loadState === 'idle' && !isLoading ? (
                    <p className="mt-2 text-xs text-slate-500">Loading tables from all schemas…</p>
                  ) : null}
                  <ul className="mt-2 space-y-1 text-sm">
                    {tables.map(t => {
                      const label = [t.schema, t.name].filter(Boolean).join('.')
                      const checked = selectedTables.some(x => x.connectionId === connector.id && x.qualified === label)
                      return (
                        <li key={`${connector.id}-${label}`}>
                          <label className="flex cursor-pointer items-center gap-2">
                            <input type="checkbox" checked={checked} onChange={() => toggleTable(connector, label)} />
                            {label}
                          </label>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              )})}
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="mt-4 space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <button type="button" className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold" onClick={acceptAll}>
                Accept all
              </button>
              <button type="button" className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold" onClick={rejectAll}>
                Reject all
              </button>
            </div>
            {SECTIONS.map(section => {
              const items = (suggestions?.[section.key] as SuggestionItem[] | undefined) ?? []
              if (!items.length) return null
              return (
                <div key={section.key} className="rounded-lg border border-slate-100 p-3">
                  <div className="text-xs font-semibold uppercase text-slate-500">{section.label}</div>
                  <ul className="mt-2 space-y-2">
                    {items.map(item => {
                      const sid = String(item.suggestion_id ?? `${section.type}:${item.key}`)
                      const d = decisions[sid]
                      if (!d) return null
                      return (
                        <li key={sid} className="rounded border border-slate-100 px-2 py-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-violet-800">Suggested</span>
                              <span className="ml-2 font-medium">{d.editing ? d.edits.name ?? labelFor(item) : labelFor({ ...item, ...d.edits })}</span>
                            </div>
                            <div className="flex gap-1">
                              <button type="button" className="text-xs text-slate-700" onClick={() => setDecision(sid, { editing: !d.editing })}>
                                Edit
                              </button>
                              <button type="button" className={`text-xs ${d.accepted ? 'font-semibold text-emerald-700' : 'text-slate-500'}`} onClick={() => setDecision(sid, { accepted: true })}>
                                Accept
                              </button>
                              <button type="button" className={`text-xs ${!d.accepted ? 'font-semibold text-red-700' : 'text-slate-500'}`} onClick={() => setDecision(sid, { accepted: false })}>
                                Reject
                              </button>
                            </div>
                          </div>
                          {d.editing ? (
                            <input
                              className="mt-2 w-full rounded border border-slate-200 px-2 py-1 text-sm"
                              value={d.edits.name ?? labelFor(item)}
                              onChange={e => setDecision(sid, { edits: { ...d.edits, name: e.target.value } })}
                            />
                          ) : null}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )
            })}
            {!suggestions ? <p className="text-xs text-slate-500">No suggestions loaded — selected tables will still be imported as data models.</p> : null}
          </div>
        ) : null}

        {step === 4 && completion ? (
          <div className="mt-4 space-y-3 text-sm" data-testid="wizard-completion">
            <p className="font-semibold text-emerald-800">Semantic model created</p>
            <ul className="grid grid-cols-2 gap-2 text-slate-700">
              <li>{completion.counts.entities ?? 0} Data Models</li>
              <li>{completion.counts.metrics ?? 0} Metrics</li>
              <li>{completion.counts.dimensions ?? 0} Dimensions</li>
              <li>{completion.counts.relationships ?? 0} Relationships</li>
            </ul>
            <p className="text-xs text-slate-500">State: Draft — publish when ready.</p>
            <div className="flex gap-2">
              <button type="button" className="btn-primary h-9 px-3 text-sm" onClick={() => onCreated(completion.modelId)}>
                Open Semantic Model
              </button>
              <Link href="/" className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold leading-9">
                Ask Data
              </Link>
            </div>
          </div>
        ) : null}

        {step < 4 ? (
          <div className="mt-6 flex justify-between gap-2">
            <button type="button" className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm" onClick={onClose}>
              Cancel
            </button>
            <div className="flex gap-2">
              {step > 1 ? (
                <button type="button" className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm" onClick={() => setStep(s => s - 1)}>
                  Back
                </button>
              ) : null}
              {step === 1 ? (
                <button type="button" className="btn-primary h-9 px-3 text-sm" disabled={!name.trim()} onClick={() => setStep(2)}>
                  Next
                </button>
              ) : null}
              {step === 2 ? (
                <button type="button" className="btn-primary h-9 px-3 text-sm" disabled={!selectedTables.length || busy} onClick={() => void loadSuggestions()}>
                  Review suggestions
                </button>
              ) : null}
              {step === 3 ? (
                <button type="button" className="btn-primary h-9 px-3 text-sm" disabled={busy || !name.trim()} onClick={() => void finishCreate()}>
                  Finish
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
