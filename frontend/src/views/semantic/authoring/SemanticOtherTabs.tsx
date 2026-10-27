'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { SortableColumnHeader } from '../../../components/table/SortableColumnHeader'
import { RowActionsMenu } from '../../../components/table/RowActionsMenu'
import { api } from '../../../lib/api'
import { safeErrorMessage } from '../../../lib/apiError'
import type {
  SemanticDimensionRecord,
  SemanticEntityRecord,
  SemanticMetricRecord,
  SemanticRelationshipRecord,
  SemanticTermRecord,
} from '../../../types/api'
import { SemanticAuthoringTableShell } from './SemanticAuthoringTableShell'
import { SemanticDrawer } from './SemanticDrawer'
import { GlossaryRelatedObjectPicker, type GlossaryRelatedOption } from './GlossaryRelatedObjectPicker'
import { SemanticAuthoringSelectCell, SemanticAuthoringSelectHeader } from './SemanticAuthoringSelectionCells'
import { useRegisterEditorDirty } from './EditorDirtyContext'
import { formatSemanticModified, semanticKeyFromName } from './semanticFormat'
import {
  buildRelationshipJoinExpression,
  defaultRelationshipDraft,
  parseRelationshipJoinExpression,
} from './relationshipJoin'
import {
  dimensionsForMetric,
  formatMetricDimensionsCell,
  measureColumnOptions,
  parseColumnFromExpression,
  physicalColumnsFromEntity,
  type PhysicalColumnMeta,
} from './metricAuthoring'
import { validateMetricDraftLocal, type MetricFieldIssue } from './metricValidation'
import { useSemanticPaginatedList } from './useSemanticPaginatedList'
import {
  SemanticSelectionBar,
  useSemanticAuthoringSelection,
  useSemanticBulkDeleteAction,
} from './useSemanticAuthoringSelection'
import { useSemanticTabObjectFocus } from './useSemanticTabObjectFocus'
import { SEMANTIC_API_MAX_PAGE_SIZE } from './semanticTableConstants'

type TabProps = {
  versionId: string | null
  readOnly: boolean
  entityKeys: string[]
  onChanged: () => void
  focusObjectId?: string | null
  onFocusObjectConsumed?: () => void
}

const COLUMN_PICK_MANUAL = '__manual__'

const CALC_TYPES = [
  { id: 'sum', label: 'Sum', aggregation: 'sum', prefix: 'SUM(' },
  { id: 'count', label: 'Count', aggregation: 'count', prefix: 'COUNT(' },
  { id: 'count_distinct', label: 'Count distinct', aggregation: 'count_distinct', prefix: 'COUNT(DISTINCT ' },
  { id: 'avg', label: 'Average', aggregation: 'avg', prefix: 'AVG(' },
  { id: 'min', label: 'Min', aggregation: 'min', prefix: 'MIN(' },
  { id: 'max', label: 'Max', aggregation: 'max', prefix: 'MAX(' },
  { id: 'formula', label: 'Formula', aggregation: null, prefix: '' },
] as const

function parseSynonyms(text: string): string[] {
  return text.split(',').map(s => s.trim()).filter(Boolean)
}

function synonymsText(values: string[] | undefined): string {
  return (values ?? []).join(', ')
}

function issueMessage(issues: MetricFieldIssue[], field: string): string | undefined {
  return issues.find(i => i.field === field)?.message
}

function useSelectionListClear(
  selection: ReturnType<typeof useSemanticAuthoringSelection>['selection'],
  list: ReturnType<typeof useSemanticPaginatedList<unknown>>,
) {
  const clearSelection = selection.clear
  useEffect(() => {
    clearSelection()
  }, [list.search, list.page, list.pageSize, list.sort, list.order, clearSelection])
}

export function MetricsTab({ versionId, readOnly, entityKeys, onChanged, focusObjectId, onFocusObjectConsumed }: TabProps) {
  const fetchPage = useCallback(async (vid: string, params: Parameters<typeof api.listSemanticMetrics>[1]) => {
    const r = await api.listSemanticMetrics(vid, params)
    return { items: r.metrics, meta: r.total != null ? { total: r.total, page: r.page ?? 1, page_size: r.page_size ?? r.metrics.length } : undefined }
  }, [])
  const list = useSemanticPaginatedList(versionId, fetchPage)
  const { selection, mode: selectionMode } = useSemanticAuthoringSelection()
  const deleteSelected = useSemanticBulkDeleteAction(
    versionId,
    (vid, ids) => api.bulkDeleteSemanticMetrics(vid, { ids }),
    async () => {
      await list.reload()
      onChanged()
    },
    selection,
    selectionMode,
  )
  useSelectionListClear(selection, list)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<(SemanticMetricRecord & { synonymsText: string; calcType: string; column: string }) | null>(null)
  const [baseline, setBaseline] = useState('')
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [fieldIssues, setFieldIssues] = useState<MetricFieldIssue[]>([])
  const [dimensions, setDimensions] = useState<SemanticDimensionRecord[]>([])
  const [relationships, setRelationships] = useState<SemanticRelationshipRecord[]>([])
  const [dimensionsByEntity, setDimensionsByEntity] = useState<Record<string, SemanticDimensionRecord[]>>({})
  const [entitiesByKey, setEntitiesByKey] = useState<Record<string, SemanticEntityRecord>>({})
  const [physicalColumnsFetched, setPhysicalColumnsFetched] = useState<Record<string, PhysicalColumnMeta[]>>({})

  useEffect(() => {
    if (!versionId) return
    void Promise.all([
      api.listSemanticDimensions(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
      api.listSemanticRelationships(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
      api.listSemanticEntities(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
    ]).then(([dimRes, relRes, entRes]) => {
      setDimensions(dimRes.dimensions)
      setRelationships(relRes.relationships)
      const byKey: Record<string, SemanticEntityRecord> = {}
      for (const entity of entRes.entities) {
        byKey[entity.key] = entity
      }
      setEntitiesByKey(prev => ({ ...byKey, ...prev }))
      for (const entity of entRes.entities) {
        if (physicalColumnsFromEntity(entity).length) continue
        const table = entity.table_name || entity.view_name
        if (!entity.connection_id || !table) continue
        void api
          .previewSemanticEntityImport(versionId, {
            connector_id: entity.connection_id,
            catalog: entity.catalog,
            schema: entity.schema,
            table,
          })
          .then(res => {
            const cols = res.preview.columns.map(c => ({
              name: c.name,
              normalized_type: c.normalized_type,
            }))
            setPhysicalColumnsFetched(prev => ({ ...prev, [entity.key]: cols }))
            if (!readOnly) {
              void api.patchSemanticEntity(versionId, entity.id, {
                metadata: { ...entity.metadata, physical_columns: cols },
              })
            }
          })
          .catch(() => undefined)
      }
    })
  }, [versionId, list.items.length, readOnly])

  useEffect(() => {
    if (!versionId || !open) return
    let cancelled = false
    void Promise.all([
      api.listSemanticDimensions(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
      api.listSemanticEntities(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
    ])
      .then(([dimRes, entRes]) => {
        if (cancelled) return
        const map: Record<string, SemanticDimensionRecord[]> = {}
        for (const dim of dimRes.dimensions) {
          map[dim.source_entity_key] = map[dim.source_entity_key] ?? []
          map[dim.source_entity_key].push(dim)
        }
        setDimensionsByEntity(map)
        const byKey: Record<string, SemanticEntityRecord> = {}
        for (const entity of entRes.entities) {
          byKey[entity.key] = entity
        }
        setEntitiesByKey(byKey)
      })
      .catch(() => {
        if (!cancelled) {
          setDimensionsByEntity({})
          setEntitiesByKey({})
        }
      })
    return () => {
      cancelled = true
    }
  }, [versionId, open, list.items.length])

  useEffect(() => {
    if (!versionId || !open || !form) return
    const entity = entitiesByKey[form.source_entity_key]
    if (!entity?.connection_id) return
    if (physicalColumnsFromEntity(entity).length) return
    const table = entity.table_name || entity.view_name
    if (!table) return
    let cancelled = false
    void api
      .previewSemanticEntityImport(versionId, {
        connector_id: entity.connection_id,
        catalog: entity.catalog,
        schema: entity.schema,
        table,
      })
      .then(res => {
        if (cancelled) return
        setPhysicalColumnsFetched(prev => ({
          ...prev,
          [entity.key]: res.preview.columns.map(c => ({
            name: c.name,
            normalized_type: c.normalized_type,
          })),
        }))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [versionId, open, form?.source_entity_key, entitiesByKey])

  const entitiesForMeasure = useMemo(() => {
    const out = { ...entitiesByKey }
    for (const [key, cols] of Object.entries(physicalColumnsFetched)) {
      const entity = out[key]
      if (!entity || physicalColumnsFromEntity(entity).length) continue
      out[key] = { ...entity, metadata: { ...entity.metadata, physical_columns: cols } }
    }
    return out
  }, [entitiesByKey, physicalColumnsFetched])

  const columnOptions = useMemo(() => {
    if (!form) return []
    return measureColumnOptions(form.source_entity_key, dimensionsByEntity, entitiesForMeasure, form.calcType)
  }, [form, dimensionsByEntity, entitiesForMeasure])

  const breakdownDimensionOptions = useMemo(() => {
    if (!form) return []
    return dimensionsForMetric(form.source_entity_key, dimensions, relationships)
  }, [form, dimensions, relationships])

  const localIssues = useMemo(() => {
    if (!form) return []
    return validateMetricDraftLocal(form, entityKeys, dimensions, relationships, list.items, entitiesForMeasure)
  }, [form, entityKeys, dimensions, relationships, list.items, entitiesForMeasure])

  const handleSave = useCallback(async () => {
    if (!form || !versionId) return
    const local = validateMetricDraftLocal(form, entityKeys, dimensions, relationships, list.items, entitiesForMeasure)
    setFieldIssues(local)
    if (local.length) {
      setErrors(local.length > 1 ? [`${local.length} validation issues`] : [local[0].message])
      throw new Error('validation')
    }
    const server = await api.validateSemanticMetric(versionId, {
      metric_id: form.id || null,
      name: form.name,
      business_definition: form.business_definition,
      expression: form.expression,
      aggregation: form.aggregation,
      source_entity_key: form.source_entity_key,
      allowed_dimension_keys: form.allowed_dimension_keys ?? [],
    })
    if (!server.valid) {
      setFieldIssues(server.issues)
      setErrors(server.form_message ? [server.form_message] : server.issues.map(i => i.message))
      throw new Error('validation')
    }
    setSaving(true)
    setErrors([])
    setFieldIssues([])
    try {
      const body = {
        name: form.name,
        business_definition: form.business_definition,
        expression: form.expression,
        aggregation: form.aggregation,
        source_entity_key: form.source_entity_key,
        synonyms: parseSynonyms(form.synonymsText),
        allowed_dimension_keys: form.allowed_dimension_keys ?? [],
      }
      if (form.id) await api.patchSemanticMetric(versionId, form.id, body)
      else
        await api.createSemanticMetric(versionId, {
          ...body,
          key: semanticKeyFromName(form.name),
        })
      setOpen(false)
      setForm(null)
      await list.reload()
      onChanged()
    } catch (err) {
      setErrors([err instanceof Error ? err.message : 'Save failed'])
      throw err
    } finally {
      setSaving(false)
    }
  }, [form, versionId, entityKeys, dimensions, relationships, list, onChanged, entitiesForMeasure])

  useRegisterEditorDirty(
    useMemo(
      () =>
        open && form
          ? { isDirty: () => JSON.stringify(form) !== baseline, save: handleSave, discard: () => { setOpen(false); setForm(null) } }
          : null,
      [open, form, baseline, handleSave],
    ),
  )

  function openCreate() {
    const seed = {
      id: '',
      key: '',
      name: '',
      description: null,
      business_definition: '',
      expression: 'SUM(amount)',
      aggregation: 'sum',
      source_entity_key: entityKeys[0] ?? '',
      format: null,
      unit: null,
      synonyms: [] as string[],
      allowed_dimension_keys: [] as string[],
      metadata: {},
      synonymsText: '',
      calcType: 'sum',
      column: 'amount',
    }
    setForm(seed)
    setBaseline(JSON.stringify(seed))
    setOpen(true)
  }

  const openEdit = useCallback((m: SemanticMetricRecord) => {
    const seed = {
      ...m,
      allowed_dimension_keys: m.allowed_dimension_keys ?? [],
      synonymsText: synonymsText(m.synonyms),
      calcType: m.aggregation ?? 'formula',
      column: parseColumnFromExpression(m.expression),
    }
    setForm(seed)
    setBaseline(JSON.stringify(seed))
    setOpen(true)
  }, [])

  const fetchAllMetrics = useCallback(async (vid: string) => {
    const r = await api.listSemanticMetrics(vid, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE })
    return r.metrics
  }, [])

  useSemanticTabObjectFocus(focusObjectId, versionId, fetchAllMetrics, openEdit, onFocusObjectConsumed)

  function applyCalcType(calcType: string, column: string) {
    if (!form) return
    const t = CALC_TYPES.find(c => c.id === calcType)
    if (!t || calcType === 'formula') {
      setForm({ ...form, calcType, aggregation: t?.aggregation ?? null })
      return
    }
    const expr = column.trim() ? `${t.prefix}${column.trim()})` : form.expression
    setForm({ ...form, calcType, aggregation: t.aggregation, expression: expr, column })
  }

  const handleDeleteMetric = useCallback(
    async (metric: SemanticMetricRecord) => {
      if (!versionId || readOnly) return
      await api.deleteSemanticMetric(versionId, metric.id)
      await list.reload()
      onChanged()
    },
    [versionId, readOnly, list, onChanged],
  )

  const colSpan = selectionMode.active ? 9 : 8
  const saveDisabled = open && form ? localIssues.length > 0 : false
  return (
    <>
      <SemanticAuthoringTableShell
        testId="semantic-metrics-table"
        searchPlaceholder="Search metrics…"
        search={list.search}
        onSearchChange={list.setSearch}
        loading={list.loading}
        error={list.error}
        onRetry={() => void list.reload()}
        emptyMessage="No business metrics yet. Create a metric to define trusted calculations for Ask Data."
        emptyColSpan={colSpan}
        hasRows={list.items.length > 0}
        addLabel="+ Add metric"
        onAdd={openCreate}
        addDisabled={readOnly || !entityKeys.length}
        readOnly={readOnly}
        selectionMode={selectionMode}
        selectionBar={
          <SemanticSelectionBar
            entityLabel="metrics"
            selectedCount={selection.selectedCount}
            onDelete={() => void deleteSelected()}
            onCancel={() => selectionMode.exit()}
          />
        }
        page={list.page}
        pageSize={list.pageSize}
        total={list.total}
        onPageChange={list.setPage}
        onPageSizeChange={list.setPageSize}
      >
        <thead className="app-table-head">
          <tr>
            <SemanticAuthoringSelectHeader active={selectionMode.active} pageIds={list.items.map(m => m.id)} selection={selection} />
            <th className="px-3 py-2"><SortableColumnHeader label="Metric" field="name" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
            <th className="px-3 py-2">Business definition</th>
            <th className="px-3 py-2">Calculation</th>
            <th className="px-3 py-2">Data model</th>
            <th className="px-3 py-2">Dimensions</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2"><SortableColumnHeader label="Modified" field="modified" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
            <th className="w-24 px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {list.items.map(m => (
            <tr key={m.id} className="h-11 border-b border-slate-50">
              <SemanticAuthoringSelectCell active={selectionMode.active} id={m.id} label={m.name} selection={selection} />
              <td className="truncate px-3 py-2 font-medium">{m.name}</td>
              <td className="truncate px-3 py-2">{m.business_definition ?? '—'}</td>
              <td className="truncate font-mono">{m.expression}</td>
              <td>{m.source_entity_key}</td>
              <td className="truncate text-xs" title={formatMetricDimensionsCell(m, dimensions, relationships)}>
                {formatMetricDimensionsCell(m, dimensions, relationships)}
              </td>
              <td className="text-emerald-800">Ready</td>
              <td>{formatSemanticModified(m.modified_at)}</td>
              <td className="px-3 py-2">
                <RowActionsMenu
                  label={`Actions for ${m.name}`}
                  items={[
                    { key: 'edit', label: 'Edit', onClick: () => openEdit(m) },
                    ...(readOnly
                      ? []
                      : [
                          { key: 'sep', separator: true as const },
                          {
                            key: 'delete',
                            label: 'Delete',
                            danger: true as const,
                            onClick: () => void handleDeleteMetric(m),
                          },
                        ]),
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </SemanticAuthoringTableShell>
      <SemanticDrawer
        open={open && !!form}
        title={form?.id ? 'Edit metric' : 'Add metric'}
        onClose={() => setOpen(false)}
        onCancel={() => setOpen(false)}
        onSave={() => void handleSave()}
        saving={saving}
        saveDisabled={saveDisabled}
        errors={errors}
      >
        {form ? (
          <div className="grid gap-3">
            <label className="block">
              <input className="w-full rounded-lg border px-3 py-2" placeholder="Metric name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
              {issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'name') ? (
                <span className="mt-1 block text-xs text-red-700">{issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'name')}</span>
              ) : null}
            </label>
            <label className="block">
              <textarea className="w-full rounded-lg border px-3 py-2" placeholder="Business definition" value={form.business_definition ?? ''} onChange={e => setForm({ ...form, business_definition: e.target.value })} />
              {issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'business_definition') ? (
                <span className="mt-1 block text-xs text-red-700">{issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'business_definition')}</span>
              ) : null}
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-slate-700">Data model (measure lives here)</span>
              <select
                className="w-full rounded-lg border px-3 py-2"
                value={form.source_entity_key}
                onChange={e => {
                  const nextEntity = e.target.value
                  const avail = new Set(
                    dimensionsForMetric(nextEntity, dimensions, relationships).map(d => d.key),
                  )
                  const kept = (form.allowed_dimension_keys ?? []).filter(k => avail.has(k))
                  setForm({ ...form, source_entity_key: nextEntity, allowed_dimension_keys: kept })
                }}
              >
                {entityKeys.map(k => (<option key={k} value={k}>{k}</option>))}
              </select>
              {issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'source_entity_key') ? (
                <span className="mt-1 block text-xs text-red-700">{issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'source_entity_key')}</span>
              ) : null}
            </label>
            <select className="rounded-lg border px-3 py-2" value={form.calcType} onChange={e => applyCalcType(e.target.value, form.column)}>
              {CALC_TYPES.map(t => (<option key={t.id} value={t.id}>{t.label}</option>))}
            </select>
            {form.calcType !== 'formula' ? (
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-slate-700">Measure column</span>
                <p className="mb-1 text-xs text-slate-500">
                  Measure columns are numeric fields (e.g. <span className="font-mono">amount</span>), not string dimensions like channel or transaction type. Use{' '}
                  <span className="font-semibold">Allowed dimensions</span> below for breakdowns.
                </p>
                <EntitySourceColumnSelect
                  entityKey={form.source_entity_key}
                  value={form.column}
                  columnOptions={columnOptions}
                  onChange={col => applyCalcType(form.calcType, col)}
                />
              </label>
            ) : (
              <label className="block">
                <input className="w-full rounded-lg border px-3 py-2 font-mono text-xs" placeholder="Expression" value={form.expression} onChange={e => setForm({ ...form, expression: e.target.value })} />
              </label>
            )}
            {issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'expression') ? (
              <span className="text-xs text-red-700">{issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'expression')}</span>
            ) : null}
            <fieldset className="rounded-lg border border-slate-200 px-3 py-2">
              <legend className="px-1 text-xs font-semibold text-slate-700">Allowed dimensions (Ask Data breakdowns)</legend>
              <p className="mb-2 text-xs text-slate-500">
                Pick which dimensions can slice this metric. Naming a metric &quot;by City&quot; does not add a breakdown — select dimensions here (and define joins under Relationships for other models).
              </p>
              {breakdownDimensionOptions.length ? (
                <ul className="max-h-40 space-y-1 overflow-y-auto">
                  {breakdownDimensionOptions.map(d => {
                    const checked = (form.allowed_dimension_keys ?? []).includes(d.key)
                    return (
                      <li key={d.key}>
                        <label className="flex cursor-pointer items-start gap-2 text-sm">
                          <input
                            type="checkbox"
                            className="mt-0.5"
                            checked={checked}
                            onChange={() => {
                              const cur = form.allowed_dimension_keys ?? []
                              const next = checked ? cur.filter(k => k !== d.key) : [...cur, d.key]
                              setForm({ ...form, allowed_dimension_keys: next })
                            }}
                          />
                          <span>
                            <span className="font-medium">{d.name}</span>
                            <span className="text-xs text-slate-500">
                              {' '}
                              · {d.key} · {d.source_entity_key}
                            </span>
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <p className="text-xs text-amber-800">Add dimensions on this model (or related models via Relationships) first.</p>
              )}
              {!form.allowed_dimension_keys?.length && breakdownDimensionOptions.length ? (
                <p className="mt-2 text-xs text-slate-500">None selected — publish will allow all listed dimensions above.</p>
              ) : null}
              {issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'allowed_dimension_keys') ? (
                <span className="mt-1 block text-xs text-red-700">
                  {issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'allowed_dimension_keys')}
                </span>
              ) : null}
            </fieldset>
            <input className="rounded-lg border px-3 py-2" placeholder="Synonyms (comma-separated)" value={form.synonymsText} onChange={e => setForm({ ...form, synonymsText: e.target.value })} />
          </div>
        ) : null}
      </SemanticDrawer>
    </>
  )
}

function entityColumnOptions(
  entityKey: string,
  dimensionsByEntity: Record<string, SemanticDimensionRecord[]>,
  entitiesByKey: Record<string, SemanticEntityRecord>,
): string[] {
  const cols = (dimensionsByEntity[entityKey] ?? []).map(d => d.source_column).filter(Boolean)
  const pk = entitiesByKey[entityKey]?.primary_key?.trim()
  if (pk) cols.push(pk)
  return Array.from(new Set(cols)).sort((a, b) => a.localeCompare(b))
}

function EntitySourceColumnSelect(props: {
  entityKey: string
  value: string
  columnOptions: string[]
  onChange: (column: string) => void
}) {
  const trimmed = props.value.trim()
  const inList = trimmed && props.columnOptions.includes(trimmed)
  const [manual, setManual] = useState(() => Boolean(trimmed && props.columnOptions.length > 0 && !inList))

  useEffect(() => {
    setManual(Boolean(trimmed && props.columnOptions.length > 0 && !props.columnOptions.includes(trimmed)))
  }, [props.entityKey, trimmed, props.columnOptions])

  if (manual || props.columnOptions.length === 0) {
    return (
      <div className="grid gap-1">
        {props.columnOptions.length === 0 ? (
          <p className="text-xs text-amber-800">
            No columns on this model yet — type the physical column name, or add another dimension first.
          </p>
        ) : (
          <p className="text-xs text-slate-500">Type a physical column name, or pick from the list.</p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm"
            value={props.value}
            onChange={e => props.onChange(e.target.value)}
            placeholder="Source column"
            list={props.columnOptions.length ? `dim-col-${props.entityKey}` : undefined}
          />
          {props.columnOptions.length > 0 ? (
            <button
              type="button"
              className="text-xs font-semibold text-cloudera-violet"
              onClick={() => {
                setManual(false)
                props.onChange('')
              }}
            >
              Pick from list
            </button>
          ) : null}
          {props.columnOptions.length > 0 ? (
            <datalist id={`dim-col-${props.entityKey}`}>
              {props.columnOptions.map(option => (
                <option key={option} value={option} />
              ))}
            </datalist>
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <div className="grid gap-1">
      <p className="text-xs text-slate-500">Choose a column already used on this data model (avoids typos).</p>
      <select
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        value={inList ? trimmed : ''}
        onChange={e => {
          const next = e.target.value
          if (next === COLUMN_PICK_MANUAL) {
            setManual(true)
            return
          }
          if (next) props.onChange(next)
        }}
      >
        <option value="">Select column…</option>
        {props.columnOptions.map(option => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
        <option value={COLUMN_PICK_MANUAL}>Type column manually…</option>
      </select>
    </div>
  )
}

export function DimensionsTab({ versionId, readOnly, entityKeys, onChanged, focusObjectId, onFocusObjectConsumed }: TabProps) {
  const fetchPage = useCallback(async (vid: string, params: Parameters<typeof api.listSemanticDimensions>[1]) => {
    const r = await api.listSemanticDimensions(vid, params)
    return { items: r.dimensions, meta: r.total != null ? { total: r.total, page: r.page ?? 1, page_size: r.page_size ?? r.dimensions.length } : undefined }
  }, [])
  const list = useSemanticPaginatedList(versionId, fetchPage)
  const { selection, mode: selectionMode } = useSemanticAuthoringSelection()
  const deleteSelected = useSemanticBulkDeleteAction(
    versionId,
    (vid, ids) => api.bulkDeleteSemanticDimensions(vid, { ids }),
    async () => {
      await list.reload()
      onChanged()
    },
    selection,
    selectionMode,
  )
  useSelectionListClear(selection, list)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<(SemanticDimensionRecord & { synonymsText: string; category: string }) | null>(null)
  const [baseline, setBaseline] = useState('')
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [dimensionsByEntity, setDimensionsByEntity] = useState<Record<string, SemanticDimensionRecord[]>>({})
  const [entitiesByKey, setEntitiesByKey] = useState<Record<string, SemanticEntityRecord>>({})

  useEffect(() => {
    if (!versionId || !open) return
    let cancelled = false
    void Promise.all([
      api.listSemanticDimensions(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
      api.listSemanticEntities(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
    ])
      .then(([dimRes, entRes]) => {
        if (cancelled) return
        const map: Record<string, SemanticDimensionRecord[]> = {}
        for (const dim of dimRes.dimensions) {
          const key = dim.source_entity_key
          map[key] = map[key] ?? []
          map[key].push(dim)
        }
        setDimensionsByEntity(map)
        const byKey: Record<string, SemanticEntityRecord> = {}
        for (const entity of entRes.entities) {
          byKey[entity.key] = entity
        }
        setEntitiesByKey(byKey)
      })
      .catch(() => {
        if (!cancelled) {
          setDimensionsByEntity({})
          setEntitiesByKey({})
        }
      })
    return () => {
      cancelled = true
    }
  }, [versionId, open, list.items.length])

  const columnOptions = useMemo(() => {
    if (!form) return []
    return entityColumnOptions(form.source_entity_key, dimensionsByEntity, entitiesByKey)
  }, [form, dimensionsByEntity, entitiesByKey])

  const handleSave = useCallback(async () => {
    if (!form || !versionId) return
    if (!form.name.trim() || !form.source_column.trim()) {
      setErrors(['Name and source field are required.'])
      throw new Error('validation')
    }
    setSaving(true)
    try {
      const body = { name: form.name, description: form.description, source_entity_key: form.source_entity_key, source_column: form.source_column, data_type: form.data_type, synonyms: parseSynonyms(form.synonymsText), metadata: { ...(form.metadata ?? {}), category: form.category } }
      if (form.id) await api.patchSemanticDimension(versionId, form.id, body)
      else await api.createSemanticDimension(versionId, { ...body, key: semanticKeyFromName(form.name) })
      setOpen(false)
      await list.reload()
      onChanged()
    } finally {
      setSaving(false)
    }
  }, [form, versionId, list, onChanged])

  useRegisterEditorDirty(useMemo(() => (open && form ? { isDirty: () => JSON.stringify(form) !== baseline, save: handleSave, discard: () => setOpen(false) } : null), [open, form, baseline, handleSave]))

  const openDimensionEdit = useCallback((d: SemanticDimensionRecord) => {
    setForm({
      ...d,
      synonymsText: synonymsText(d.synonyms),
      category: String((d.metadata as { category?: string })?.category ?? 'Other'),
    })
    setBaseline(JSON.stringify(d))
    setOpen(true)
  }, [])

  const fetchAllDimensions = useCallback(async (vid: string) => {
    const r = await api.listSemanticDimensions(vid, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE })
    return r.dimensions
  }, [])

  useSemanticTabObjectFocus(focusObjectId, versionId, fetchAllDimensions, openDimensionEdit, onFocusObjectConsumed)

  return (
    <>
      <SemanticAuthoringTableShell testId="semantic-dimensions-table" searchPlaceholder="Search dimensions…" search={list.search} onSearchChange={list.setSearch} loading={list.loading} error={list.error} onRetry={() => void list.reload()} emptyMessage="No dimensions yet." emptyColSpan={selectionMode.active ? 10 : 9} hasRows={list.items.length > 0} addLabel="+ Add dimension" onAdd={() => { setForm({ id: '', key: '', name: '', description: '', source_entity_key: entityKeys[0] ?? '', source_column: '', data_type: '', synonyms: [], metadata: {}, synonymsText: '', category: 'Other' }); setBaseline(''); setOpen(true) }} addDisabled={readOnly} readOnly={readOnly} selectionMode={selectionMode} selectionBar={<SemanticSelectionBar entityLabel="dimensions" selectedCount={selection.selectedCount} onDelete={() => void deleteSelected()} onCancel={() => selectionMode.exit()} />} page={list.page} pageSize={list.pageSize} total={list.total} onPageChange={list.setPage} onPageSizeChange={list.setPageSize}>
        <thead className="app-table-head"><tr>
          <SemanticAuthoringSelectHeader active={selectionMode.active} pageIds={list.items.map(d => d.id)} selection={selection} />
          <th className="px-3 py-2"><SortableColumnHeader label="Dimension" field="name" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
          <th className="px-3 py-2">Business definition</th><th className="px-3 py-2">Data model</th><th className="px-3 py-2">Source field</th><th className="px-3 py-2">Category</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Status</th>
          <th className="px-3 py-2"><SortableColumnHeader label="Modified" field="modified" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
          <th className="w-24 px-3 py-2">Actions</th>
        </tr></thead>
        <tbody>{list.items.map(d => (
          <tr key={d.id} className="h-11 border-b border-slate-50">
            <SemanticAuthoringSelectCell active={selectionMode.active} id={d.id} label={d.name} selection={selection} />
            <td className="px-3 py-2 font-medium">{d.name}</td><td className="px-3 py-2">{d.description ?? '—'}</td><td className="px-3 py-2">{d.source_entity_key}</td><td className="px-3 py-2">{d.source_column}</td>
            <td className="px-3 py-2">{String((d.metadata as { category?: string })?.category ?? 'Other')}</td><td className="px-3 py-2">{d.data_type ?? '—'}</td><td className="px-3 py-2 text-emerald-800">Ready</td>
            <td className="px-3 py-2">{formatSemanticModified(d.modified_at)}</td>
            <td className="px-3 py-2"><RowActionsMenu label={`Edit ${d.name}`} items={[{ key: 'e', label: 'Edit', onClick: () => openDimensionEdit(d) }]} /></td>
          </tr>
        ))}</tbody>
      </SemanticAuthoringTableShell>
      <SemanticDrawer open={open && !!form} title="Dimension" onClose={() => setOpen(false)} onCancel={() => setOpen(false)} onSave={() => void handleSave()} saving={saving} errors={errors}>
        {form ? (<div className="grid gap-2">
          <input className="rounded border px-3 py-2" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Name" />
          <textarea className="rounded border px-3 py-2" value={form.description ?? ''} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Business definition" />
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-slate-700">Data model</span>
            <select
              className="w-full rounded-lg border border-slate-200 px-3 py-2"
              value={form.source_entity_key}
              onChange={e => setForm({ ...form, source_entity_key: e.target.value, source_column: '' })}
            >
              {entityKeys.map(k => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-semibold text-slate-700">Source column</span>
            <EntitySourceColumnSelect
              entityKey={form.source_entity_key}
              value={form.source_column}
              columnOptions={columnOptions}
              onChange={source_column => setForm({ ...form, source_column })}
            />
          </label>
          <select className="rounded border px-3 py-2" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
            {['Time', 'Geography', 'Product', 'Customer', 'Other'].map(c => <option key={c}>{c}</option>)}
          </select>
          <input className="rounded border px-3 py-2" value={form.data_type ?? ''} onChange={e => setForm({ ...form, data_type: e.target.value })} placeholder="Type" />
        </div>) : null}
      </SemanticDrawer>
    </>
  )
}

type RelationshipFormState = SemanticRelationshipRecord & {
  from_key_columns: string[]
  to_key_columns: string[]
  use_advanced_join: boolean
}

const RELATIONSHIP_TYPES = [
  { value: 'many_to_one', label: 'Many-to-one (many From rows → one To row)' },
  { value: 'one_to_many', label: 'One-to-many (one From row → many To rows)' },
  { value: 'one_to_one', label: 'One-to-one' },
  { value: 'many_to_many', label: 'Many-to-many' },
] as const

const JOIN_TYPES = [
  { value: 'inner', label: 'Inner join' },
  { value: 'left', label: 'Left join' },
  { value: 'right', label: 'Right join' },
  { value: 'full', label: 'Full outer join' },
] as const

function RelationshipKeyColumnsEditor(props: {
  label: string
  entityKey: string
  columns: string[]
  columnOptions: string[]
  onChange: (columns: string[]) => void
}) {
  const [manualRows, setManualRows] = useState<Set<number>>(() => new Set())

  useEffect(() => {
    setManualRows(new Set())
  }, [props.entityKey])

  const selectOptions = useMemo(() => {
    const set = new Set(props.columnOptions)
    for (const col of props.columns) {
      const trimmed = col.trim()
      if (trimmed) set.add(trimmed)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [props.columnOptions, props.columns])

  const updateAt = (index: number, value: string) => {
    const next = [...props.columns]
    next[index] = value
    props.onChange(next)
  }

  const rowUsesManual = (index: number, col: string) => {
    if (manualRows.has(index)) return true
    const trimmed = col.trim()
    if (!trimmed) return selectOptions.length === 0
    return selectOptions.length > 0 && !props.columnOptions.includes(trimmed)
  }

  return (
    <div className="grid gap-2">
      <span className="text-xs font-semibold text-slate-700">{props.label}</span>
      {selectOptions.length === 0 ? (
        <p className="text-xs text-amber-800">
          No columns listed for this model yet. Add dimensions on the Dimensions tab, or type the physical column name
          below.
        </p>
      ) : (
        <p className="text-xs text-slate-500">Choose from columns already defined on this model (avoids typos).</p>
      )}
      {props.columns.map((col, index) => {
        const manual = rowUsesManual(index, col)
        return (
          <div key={`${props.entityKey}-key-${index}`} className="flex flex-wrap items-center gap-2">
            {manual ? (
              <input
                className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm"
                value={col}
                onChange={e => updateAt(index, e.target.value)}
                placeholder="Physical column name"
                list={selectOptions.length ? `rel-key-${props.entityKey}-${index}` : undefined}
              />
            ) : (
              <select
                className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={col && selectOptions.includes(col.trim()) ? col.trim() : ''}
                onChange={e => {
                  const value = e.target.value
                  if (value === COLUMN_PICK_MANUAL) {
                    setManualRows(prev => new Set(prev).add(index))
                    return
                  }
                  if (value) updateAt(index, value)
                }}
              >
                <option value="">Select column…</option>
                {selectOptions.map(option => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
                <option value={COLUMN_PICK_MANUAL}>Type column manually…</option>
              </select>
            )}
            {manual && selectOptions.length > 0 ? (
              <button
                type="button"
                className="text-xs font-semibold text-cloudera-violet"
                onClick={() => {
                  setManualRows(prev => {
                    const next = new Set(prev)
                    next.delete(index)
                    return next
                  })
                  updateAt(index, '')
                }}
              >
                Pick from list
              </button>
            ) : null}
            {selectOptions.length > 0 && manual ? (
              <datalist id={`rel-key-${props.entityKey}-${index}`}>
                {selectOptions.map(option => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            ) : null}
            {props.columns.length > 1 ? (
              <button
                type="button"
                className="text-xs font-semibold text-red-700"
                onClick={() => {
                  setManualRows(prev => {
                    const next = new Set<number>()
                    for (const i of prev) {
                      if (i < index) next.add(i)
                      else if (i > index) next.add(i - 1)
                    }
                    return next
                  })
                  props.onChange(props.columns.filter((_, i) => i !== index))
                }}
              >
                Remove
              </button>
            ) : null}
          </div>
        )
      })}
      <button
        type="button"
        className="text-left text-xs font-semibold text-cloudera-violet"
        onClick={() => {
          const first = selectOptions[0] ?? ''
          props.onChange([...props.columns, first])
        }}
      >
        + Add key column
      </button>
    </div>
  )
}

export function RelationshipsTab({ versionId, readOnly, entityKeys, onChanged, focusObjectId, onFocusObjectConsumed }: TabProps) {
  const fetchPage = useCallback(async (vid: string, params: Parameters<typeof api.listSemanticRelationships>[1]) => {
    const r = await api.listSemanticRelationships(vid, params)
    return { items: r.relationships, meta: r.total != null ? { total: r.total, page: r.page ?? 1, page_size: r.page_size ?? r.relationships.length } : undefined }
  }, [])
  const list = useSemanticPaginatedList(versionId, fetchPage)
  const { selection, mode: selectionMode } = useSemanticAuthoringSelection()
  const deleteSelected = useSemanticBulkDeleteAction(
    versionId,
    (vid, ids) => api.bulkDeleteSemanticRelationships(vid, { ids }),
    async () => {
      await list.reload()
      onChanged()
    },
    selection,
    selectionMode,
  )
  useSelectionListClear(selection, list)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<RelationshipFormState | null>(null)
  const [baseline, setBaseline] = useState('')
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [dimensionsByEntity, setDimensionsByEntity] = useState<Record<string, SemanticDimensionRecord[]>>({})
  const [entitiesByKey, setEntitiesByKey] = useState<Record<string, SemanticEntityRecord>>({})

  useEffect(() => {
    if (!versionId) return
    let cancelled = false
    void Promise.all([
      api.listSemanticDimensions(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
      api.listSemanticEntities(versionId, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE }),
    ])
      .then(([dimRes, entRes]) => {
        if (cancelled) return
        const map: Record<string, SemanticDimensionRecord[]> = {}
        for (const dim of dimRes.dimensions) {
          const key = dim.source_entity_key
          map[key] = map[key] ?? []
          map[key].push(dim)
        }
        setDimensionsByEntity(map)
        const byKey: Record<string, SemanticEntityRecord> = {}
        for (const entity of entRes.entities) {
          byKey[entity.key] = entity
        }
        setEntitiesByKey(byKey)
      })
      .catch(() => {
        if (!cancelled) {
          setDimensionsByEntity({})
          setEntitiesByKey({})
        }
      })
    return () => {
      cancelled = true
    }
  }, [versionId, list.items.length])

  const columnOptionsFor = useCallback(
    (entityKey: string) => {
      const cols = (dimensionsByEntity[entityKey] ?? []).map(d => d.source_column).filter(Boolean)
      const pk = entitiesByKey[entityKey]?.primary_key?.trim()
      if (pk) cols.push(pk)
      return Array.from(new Set(cols))
    },
    [dimensionsByEntity, entitiesByKey],
  )

  const handleSave = useCallback(async () => {
    if (!form || !versionId) return
    setErrors([])
    if (!form.name.trim()) {
      setErrors(['Relationship name is required.'])
      return
    }
    if (form.from_entity_key === form.to_entity_key) {
      setErrors(['From and To must be different data models.'])
      return
    }
    const join = form.use_advanced_join
      ? form.join_expression.trim()
      : buildRelationshipJoinExpression(
          form.from_entity_key,
          form.from_key_columns,
          form.to_entity_key,
          form.to_key_columns,
        )
    if (!join) {
      setErrors(['Complete join key columns on both sides, or use the raw join expression.'])
      return
    }
    setSaving(true)
    try {
      const body = { name: form.name, from_entity_key: form.from_entity_key, to_entity_key: form.to_entity_key, join_expression: join, join_type: form.join_type, relationship_type: form.relationship_type, description: form.description }
      if (form.id) await api.patchSemanticRelationship(versionId, form.id, body)
      else await api.createSemanticRelationship(versionId, { ...body, key: semanticKeyFromName(form.name) })
      setOpen(false)
      await list.reload()
      onChanged()
    } catch (err) {
      setErrors([safeErrorMessage(err, 'Could not save relationship')])
    } finally {
      setSaving(false)
    }
  }, [form, versionId, list, onChanged])

  useRegisterEditorDirty(useMemo(() => (open && form ? { isDirty: () => JSON.stringify(form) !== baseline, save: handleSave, discard: () => setOpen(false) } : null), [open, form, baseline, handleSave]))

  const openRelationshipEdit = useCallback((r: SemanticRelationshipRecord) => {
    const parsed = parseRelationshipJoinExpression(r.join_expression, r.from_entity_key, r.to_entity_key)
    const draft: RelationshipFormState = {
      ...r,
      from_key_columns: parsed.from.length ? parsed.from : [''],
      to_key_columns: parsed.to.length ? parsed.to : [''],
      use_advanced_join: false,
    }
    setErrors([])
    setForm(draft)
    setBaseline(JSON.stringify(draft))
    setOpen(true)
  }, [])

  const openRelationshipCreate = useCallback(() => {
    const defaults = defaultRelationshipDraft(entityKeys)
    const draft: RelationshipFormState = {
      id: '',
      key: '',
      name: defaults.from_entity_key && defaults.to_entity_key ? `${defaults.from_entity_key} to ${defaults.to_entity_key}` : '',
      from_entity_key: defaults.from_entity_key,
      to_entity_key: defaults.to_entity_key,
      relationship_type: defaults.relationship_type,
      join_type: 'inner',
      join_expression: '',
      description: '',
      metadata: {},
      from_key_columns: defaults.from_key_columns,
      to_key_columns: defaults.to_key_columns,
      use_advanced_join: false,
    }
    setErrors([])
    setForm(draft)
    setBaseline(JSON.stringify(draft))
    setOpen(true)
  }, [entityKeys])

  const fetchAllRelationships = useCallback(async (vid: string) => {
    const res = await api.listSemanticRelationships(vid, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE })
    return res.relationships
  }, [])

  useSemanticTabObjectFocus(focusObjectId, versionId, fetchAllRelationships, openRelationshipEdit, onFocusObjectConsumed)

  return (
    <>
      <SemanticAuthoringTableShell testId="semantic-relationships-table" searchPlaceholder="Search relationships…" search={list.search} onSearchChange={list.setSearch} loading={list.loading} error={list.error} onRetry={() => void list.reload()} emptyMessage="No relationships defined." emptyColSpan={selectionMode.active ? 9 : 8} hasRows={list.items.length > 0} addLabel="+ Add relationship" onAdd={openRelationshipCreate} addDisabled={readOnly} readOnly={readOnly} selectionMode={selectionMode} selectionBar={<SemanticSelectionBar entityLabel="relationships" selectedCount={selection.selectedCount} onDelete={() => void deleteSelected()} onCancel={() => selectionMode.exit()} />} page={list.page} pageSize={list.pageSize} total={list.total} onPageChange={list.setPage} onPageSizeChange={list.setPageSize}>
        <thead className="app-table-head"><tr>
          <SemanticAuthoringSelectHeader active={selectionMode.active} pageIds={list.items.map(r => r.id)} selection={selection} />
          <th className="px-3 py-2">From</th><th className="px-3 py-2">Relationship</th><th className="px-3 py-2">To</th><th className="px-3 py-2">Cardinality</th><th className="px-3 py-2">Join key</th><th className="px-3 py-2">Status</th>
          <th className="px-3 py-2"><SortableColumnHeader label="Modified" field="modified" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
          <th className="w-24 px-3 py-2">Actions</th>
        </tr></thead>
        <tbody>{list.items.map(r => (
          <tr key={r.id} className="h-11 border-b">
            <SemanticAuthoringSelectCell active={selectionMode.active} id={r.id} label={r.name} selection={selection} />
            <td>{r.from_entity_key}</td><td>{r.name}</td><td>{r.to_entity_key}</td><td>{r.relationship_type}</td><td className="font-mono">{r.join_expression}</td><td className="text-emerald-800">Ready</td><td>{formatSemanticModified(r.modified_at)}</td>
            <td className="px-3 py-2"><RowActionsMenu label="Edit" items={[{ key: 'e', label: 'Edit', onClick: () => openRelationshipEdit(r) }]} /></td>
          </tr>
        ))}</tbody>
      </SemanticAuthoringTableShell>
      <SemanticDrawer
        open={open && !!form}
        title="Relationship"
        onClose={() => setOpen(false)}
        onCancel={() => setOpen(false)}
        onSave={() => void handleSave()}
        saving={saving}
        errors={errors}
        saveDisabled={
          !!form &&
          !form.use_advanced_join &&
          !buildRelationshipJoinExpression(
            form.from_entity_key,
            form.from_key_columns,
            form.to_entity_key,
            form.to_key_columns,
          )
        }
      >
        {form ? (
          <div className="grid gap-4 text-sm">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-slate-700">Relationship name</span>
              <input
                className="w-full rounded-lg border border-slate-200 px-3 py-2"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Transactions to customers"
              />
            </label>

            <fieldset className="grid gap-3 rounded-lg border border-slate-200 p-3">
              <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">From</legend>
              <label className="block">
                <span className="mb-1 block text-xs text-slate-600">Data model</span>
                <select
                  className="w-full rounded-lg border border-slate-200 px-3 py-2"
                  value={form.from_entity_key}
                  onChange={e => setForm({ ...form, from_entity_key: e.target.value })}
                >
                  {entityKeys.map(k => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </label>
              <RelationshipKeyColumnsEditor
                label="Join key column(s)"
                entityKey={form.from_entity_key}
                columns={form.from_key_columns}
                columnOptions={columnOptionsFor(form.from_entity_key)}
                onChange={from_key_columns => setForm({ ...form, from_key_columns })}
              />
            </fieldset>

            <fieldset className="grid gap-3 rounded-lg border border-slate-200 p-3">
              <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">To</legend>
              <label className="block">
                <span className="mb-1 block text-xs text-slate-600">Data model</span>
                <select
                  className="w-full rounded-lg border border-slate-200 px-3 py-2"
                  value={form.to_entity_key}
                  onChange={e => setForm({ ...form, to_entity_key: e.target.value })}
                >
                  {entityKeys.map(k => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </label>
              <RelationshipKeyColumnsEditor
                label="Join key column(s)"
                entityKey={form.to_entity_key}
                columns={form.to_key_columns}
                columnOptions={columnOptionsFor(form.to_entity_key)}
                onChange={to_key_columns => setForm({ ...form, to_key_columns })}
              />
            </fieldset>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-slate-700">Join type</span>
                <select
                  className="w-full rounded-lg border border-slate-200 px-3 py-2"
                  value={form.join_type}
                  onChange={e => setForm({ ...form, join_type: e.target.value })}
                >
                  {JOIN_TYPES.map(j => (
                    <option key={j.value} value={j.value}>
                      {j.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-slate-700">Cardinality</span>
                <select
                  className="w-full rounded-lg border border-slate-200 px-3 py-2"
                  value={form.relationship_type}
                  onChange={e => setForm({ ...form, relationship_type: e.target.value })}
                >
                  {RELATIONSHIP_TYPES.map(r => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <p className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
              {form.use_advanced_join
                ? form.join_expression || '—'
                : buildRelationshipJoinExpression(
                    form.from_entity_key,
                    form.from_key_columns,
                    form.to_entity_key,
                    form.to_key_columns,
                  ) || 'Complete join keys to preview SQL ON clause'}
            </p>

            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-slate-700">Business description</span>
              <textarea
                className="w-full rounded-lg border border-slate-200 px-3 py-2"
                value={form.description ?? ''}
                onChange={e => setForm({ ...form, description: e.target.value })}
                placeholder="Optional"
              />
            </label>

            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={form.use_advanced_join}
                onChange={e => setForm({ ...form, use_advanced_join: e.target.checked })}
              />
              Edit raw join expression (multi-clause SQL)
            </label>
            {form.use_advanced_join ? (
              <textarea
                className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs"
                value={form.join_expression}
                onChange={e => setForm({ ...form, join_expression: e.target.value })}
                rows={4}
                placeholder="transactions.customer_id = customers.customer_id"
              />
            ) : null}
          </div>
        ) : null}
      </SemanticDrawer>
    </>
  )
}

export function GlossaryTab({
  versionId,
  readOnly,
  entityKeys,
  onChanged,
  focusObjectId,
  onFocusObjectConsumed,
}: TabProps & { metricKeys: string[]; dimensionKeys: string[] }) {
  const fetchPage = useCallback(async (vid: string, params: Parameters<typeof api.listSemanticTerms>[1]) => {
    const r = await api.listSemanticTerms(vid, params)
    return { items: r.terms, meta: r.total != null ? { total: r.total, page: r.page ?? 1, page_size: r.page_size ?? r.terms.length } : undefined }
  }, [])
  const list = useSemanticPaginatedList(versionId, fetchPage)
  const { selection, mode: selectionMode } = useSemanticAuthoringSelection()
  const deleteSelected = useSemanticBulkDeleteAction(
    versionId,
    (vid, ids) => api.bulkDeleteSemanticTerms(vid, { ids }),
    async () => {
      await list.reload()
      onChanged()
    },
    selection,
    selectionMode,
  )
  useSelectionListClear(selection, list)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<(SemanticTermRecord & { synonymsText: string }) | null>(null)
  const [baseline, setBaseline] = useState('')
  const [saving, setSaving] = useState(false)
  const [relatedOptions, setRelatedOptions] = useState<GlossaryRelatedOption[]>([])

  useEffect(() => {
    if (!versionId || !open) return
    Promise.all([
      api.listSemanticEntities(versionId, { page: 1, page_size: 200 }),
      api.listSemanticMetrics(versionId, { page: 1, page_size: 200 }),
      api.listSemanticDimensions(versionId, { page: 1, page_size: 200 }),
    ]).then(([e, m, d]) => {
      setRelatedOptions([
        ...e.entities.map(row => ({ key: row.key, label: row.name, kind: 'entity' as const })),
        ...m.metrics.map(row => ({ key: row.key, label: row.name, kind: 'metric' as const })),
        ...d.dimensions.map(row => ({ key: row.key, label: row.name, kind: 'dimension' as const })),
      ])
    })
  }, [versionId, open])

  const handleSave = useCallback(async () => {
    if (!form || !versionId) return
    setSaving(true)
    try {
      const body = { term: form.term, definition: form.definition, synonyms: parseSynonyms(form.synonymsText), related_metric_keys: form.related_metric_keys, related_dimension_keys: form.related_dimension_keys, related_entity_keys: form.related_entity_keys }
      if (form.id) await api.patchSemanticTerm(versionId, form.id, body)
      else await api.createSemanticTerm(versionId, { ...body, key: semanticKeyFromName(form.term) })
      setOpen(false)
      await list.reload()
      onChanged()
    } finally {
      setSaving(false)
    }
  }, [form, versionId, list, onChanged])

  useRegisterEditorDirty(useMemo(() => (open && form ? { isDirty: () => JSON.stringify(form) !== baseline, save: handleSave, discard: () => setOpen(false) } : null), [open, form, baseline, handleSave]))

  const handleDeleteTerm = useCallback(
    async (term: SemanticTermRecord) => {
      if (!versionId || readOnly) return
      await api.deleteSemanticTerm(versionId, term.id)
      await list.reload()
      onChanged()
    },
    [versionId, readOnly, list, onChanged],
  )

  const openTermEdit = useCallback((t: SemanticTermRecord) => {
    setForm({ ...t, synonymsText: synonymsText(t.synonyms ?? []), related_metric_keys: t.related_metric_keys ?? [], related_dimension_keys: t.related_dimension_keys ?? [], related_entity_keys: t.related_entity_keys ?? [] })
    setBaseline(JSON.stringify(t))
    setOpen(true)
  }, [])

  const fetchAllTerms = useCallback(async (vid: string) => {
    const r = await api.listSemanticTerms(vid, { page: 1, page_size: SEMANTIC_API_MAX_PAGE_SIZE })
    return r.terms
  }, [])

  useSemanticTabObjectFocus(focusObjectId, versionId, fetchAllTerms, openTermEdit, onFocusObjectConsumed)

  return (
    <>
      <SemanticAuthoringTableShell testId="semantic-glossary-table" searchPlaceholder="Search glossary…" search={list.search} onSearchChange={list.setSearch} loading={list.loading} error={list.error} onRetry={() => void list.reload()} emptyMessage="No glossary terms yet." emptyColSpan={selectionMode.active ? 7 : 6} hasRows={list.items.length > 0} addLabel="+ Add term" onAdd={() => { setForm({ id: '', key: '', term: '', definition: '', synonyms: [], related_metric_keys: [], related_dimension_keys: [], related_entity_keys: [], metadata: {}, synonymsText: '' }); setOpen(true) }} addDisabled={readOnly} readOnly={readOnly} selectionMode={selectionMode} selectionBar={<SemanticSelectionBar entityLabel="terms" selectedCount={selection.selectedCount} onDelete={() => void deleteSelected()} onCancel={() => selectionMode.exit()} />} page={list.page} pageSize={list.pageSize} total={list.total} onPageChange={list.setPage} onPageSizeChange={list.setPageSize}>
        <thead className="app-table-head"><tr>
          <SemanticAuthoringSelectHeader active={selectionMode.active} pageIds={list.items.map(t => t.id)} selection={selection} />
          <th className="px-3 py-2"><SortableColumnHeader label="Term" field="name" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
          <th className="px-3 py-2">Definition</th><th className="px-3 py-2">Synonyms</th><th className="px-3 py-2">Mapped objects</th>
          <th className="px-3 py-2"><SortableColumnHeader label="Modified" field="modified" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
          <th className="w-24 px-3 py-2">Actions</th>
        </tr></thead>
        <tbody>{list.items.map(t => (
          <tr key={t.id} className="h-11 border-b border-slate-50">
            <SemanticAuthoringSelectCell active={selectionMode.active} id={t.id} label={t.term} selection={selection} />
            <td className="truncate px-3 py-2 font-medium">{t.term}</td>
            <td className="truncate px-3 py-2">{t.definition ?? '—'}</td>
            <td className="truncate px-3 py-2">{(t.synonyms ?? []).join(', ') || '—'}</td>
            <td className="truncate px-3 py-2">
              {[...(t.related_metric_keys ?? []), ...(t.related_dimension_keys ?? [])].slice(0, 3).join(', ') || '—'}
            </td>
            <td className="px-3 py-2">{formatSemanticModified(t.modified_at)}</td>
            <td className="px-3 py-2">
              <RowActionsMenu
                label={`Actions for ${t.term}`}
                items={[
                  { key: 'edit', label: 'Edit', onClick: () => openTermEdit(t) },
                  ...(readOnly
                    ? []
                    : [
                        { key: 'sep', separator: true as const },
                        {
                          key: 'delete',
                          label: 'Delete',
                          danger: true as const,
                          onClick: () => void handleDeleteTerm(t),
                        },
                      ]),
                ]}
              />
            </td>
          </tr>
        ))}</tbody>
      </SemanticAuthoringTableShell>
      <SemanticDrawer open={open && !!form} title="Glossary term" onClose={() => setOpen(false)} onCancel={() => setOpen(false)} onSave={() => void handleSave()} saving={saving}>
        {form ? (<div className="grid gap-2">
          <input className="rounded border px-3 py-2" value={form.term} onChange={e => setForm({ ...form, term: e.target.value })} placeholder="Term" />
          <textarea className="rounded border px-3 py-2" value={form.definition ?? ''} onChange={e => setForm({ ...form, definition: e.target.value })} placeholder="Definition" />
          <input className="rounded border px-3 py-2" value={form.synonymsText} onChange={e => setForm({ ...form, synonymsText: e.target.value })} placeholder="Synonyms" />
          <GlossaryRelatedObjectPicker
            options={relatedOptions}
            selectedEntityKeys={form.related_entity_keys}
            selectedMetricKeys={form.related_metric_keys}
            selectedDimensionKeys={form.related_dimension_keys}
            onChange={({ entityKeys: ek, metricKeys: mk, dimensionKeys: dk }) =>
              setForm({
                ...form,
                related_entity_keys: ek,
                related_metric_keys: mk,
                related_dimension_keys: dk,
              })
            }
          />
        </div>) : null}
      </SemanticDrawer>
    </>
  )
}
