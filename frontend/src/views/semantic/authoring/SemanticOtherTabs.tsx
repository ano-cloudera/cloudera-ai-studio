'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { SortableColumnHeader } from '../../../components/table/SortableColumnHeader'
import { RowActionsMenu } from '../../../components/table/RowActionsMenu'
import { api } from '../../../lib/api'
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
import { validateMetricDraftLocal, type MetricFieldIssue } from './metricValidation'
import { useSemanticPaginatedList } from './useSemanticPaginatedList'
import {
  SemanticSelectionBar,
  useSemanticAuthoringSelection,
  useSemanticBulkDeleteAction,
} from './useSemanticAuthoringSelection'

type TabProps = {
  versionId: string | null
  readOnly: boolean
  entityKeys: string[]
  onChanged: () => void
}

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

export function MetricsTab({ versionId, readOnly, entityKeys, onChanged }: TabProps) {
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

  useEffect(() => {
    if (!versionId) return
    api.listSemanticDimensions(versionId, { page: 1, page_size: 200 }).then(r => setDimensions(r.dimensions))
  }, [versionId, list.items.length])

  const localIssues = useMemo(() => {
    if (!form) return []
    return validateMetricDraftLocal(form, entityKeys, dimensions, list.items)
  }, [form, entityKeys, dimensions, list.items])

  const handleSave = useCallback(async () => {
    if (!form || !versionId) return
    const local = validateMetricDraftLocal(form, entityKeys, dimensions, list.items)
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
  }, [form, versionId, entityKeys, dimensions, list, onChanged])

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
      metadata: {},
      synonymsText: '',
      calcType: 'sum',
      column: 'amount',
    }
    setForm(seed)
    setBaseline(JSON.stringify(seed))
    setOpen(true)
  }

  function openEdit(m: SemanticMetricRecord) {
    const seed = { ...m, synonymsText: synonymsText(m.synonyms), calcType: m.aggregation ?? 'formula', column: '' }
    setForm(seed)
    setBaseline(JSON.stringify(seed))
    setOpen(true)
  }

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
              <td className="truncate px-3 py-2 font-mono text-xs">{m.expression}</td>
              <td className="px-3 py-2">{m.source_entity_key}</td>
              <td className="truncate px-3 py-2 text-xs">{dimensions.slice(0, 3).map(d => d.key).join(', ') || '—'}</td>
              <td className="px-3 py-2 text-xs text-emerald-800">Ready</td>
              <td className="px-3 py-2">{formatSemanticModified(m.modified_at)}</td>
              <td className="px-3 py-2">
                <RowActionsMenu label={`Actions for ${m.name}`} items={[{ key: 'edit', label: 'Edit', onClick: () => openEdit(m) }]} />
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
              <select className="w-full rounded-lg border px-3 py-2" value={form.source_entity_key} onChange={e => setForm({ ...form, source_entity_key: e.target.value })}>
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
                <input className="w-full rounded-lg border px-3 py-2" placeholder="Column" value={form.column} onChange={e => applyCalcType(form.calcType, e.target.value)} />
              </label>
            ) : (
              <label className="block">
                <input className="w-full rounded-lg border px-3 py-2 font-mono text-xs" placeholder="Expression" value={form.expression} onChange={e => setForm({ ...form, expression: e.target.value })} />
              </label>
            )}
            {issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'expression') ? (
              <span className="text-xs text-red-700">{issueMessage(fieldIssues.length ? fieldIssues : localIssues, 'expression')}</span>
            ) : null}
            <input className="rounded-lg border px-3 py-2" placeholder="Synonyms (comma-separated)" value={form.synonymsText} onChange={e => setForm({ ...form, synonymsText: e.target.value })} />
          </div>
        ) : null}
      </SemanticDrawer>
    </>
  )
}

export function DimensionsTab({ versionId, readOnly, entityKeys, onChanged }: TabProps) {
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
            <td className="px-3 py-2"><RowActionsMenu label={`Edit ${d.name}`} items={[{ key: 'e', label: 'Edit', onClick: () => { setForm({ ...d, synonymsText: synonymsText(d.synonyms), category: String((d.metadata as { category?: string })?.category ?? 'Other') }); setBaseline(JSON.stringify(d)); setOpen(true) } }]} /></td>
          </tr>
        ))}</tbody>
      </SemanticAuthoringTableShell>
      <SemanticDrawer open={open && !!form} title="Dimension" onClose={() => setOpen(false)} onCancel={() => setOpen(false)} onSave={() => void handleSave()} saving={saving} errors={errors}>
        {form ? (<div className="grid gap-2">
          <input className="rounded border px-3 py-2" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Name" />
          <textarea className="rounded border px-3 py-2" value={form.description ?? ''} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Business definition" />
          <select className="rounded border px-3 py-2" value={form.source_entity_key} onChange={e => setForm({ ...form, source_entity_key: e.target.value })}>{entityKeys.map(k => <option key={k} value={k}>{k}</option>)}</select>
          <input className="rounded border px-3 py-2" value={form.source_column} onChange={e => setForm({ ...form, source_column: e.target.value })} placeholder="Source column" />
          <select className="rounded border px-3 py-2" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
            {['Time', 'Geography', 'Product', 'Customer', 'Other'].map(c => <option key={c}>{c}</option>)}
          </select>
          <input className="rounded border px-3 py-2" value={form.data_type ?? ''} onChange={e => setForm({ ...form, data_type: e.target.value })} placeholder="Type" />
        </div>) : null}
      </SemanticDrawer>
    </>
  )
}

export function RelationshipsTab({ versionId, readOnly, entityKeys, onChanged }: TabProps) {
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
  const [form, setForm] = useState<(SemanticRelationshipRecord & { from_field: string; to_field: string }) | null>(null)
  const [baseline, setBaseline] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = useCallback(async () => {
    if (!form || !versionId) return
    const join = form.from_field && form.to_field ? `${form.from_entity_key}.${form.from_field} = ${form.to_entity_key}.${form.to_field}` : form.join_expression
    setSaving(true)
    try {
      const body = { name: form.name, from_entity_key: form.from_entity_key, to_entity_key: form.to_entity_key, join_expression: join, join_type: form.join_type, relationship_type: form.relationship_type, description: form.description }
      if (form.id) await api.patchSemanticRelationship(versionId, form.id, body)
      else await api.createSemanticRelationship(versionId, { ...body, key: semanticKeyFromName(form.name) })
      setOpen(false)
      await list.reload()
      onChanged()
    } finally {
      setSaving(false)
    }
  }, [form, versionId, list, onChanged])

  useRegisterEditorDirty(useMemo(() => (open && form ? { isDirty: () => JSON.stringify(form) !== baseline, save: handleSave, discard: () => setOpen(false) } : null), [open, form, baseline, handleSave]))

  return (
    <>
      <SemanticAuthoringTableShell testId="semantic-relationships-table" searchPlaceholder="Search relationships…" search={list.search} onSearchChange={list.setSearch} loading={list.loading} error={list.error} onRetry={() => void list.reload()} emptyMessage="No relationships defined." emptyColSpan={selectionMode.active ? 9 : 8} hasRows={list.items.length > 0} addLabel="+ Add relationship" onAdd={() => { setForm({ id: '', key: '', name: '', from_entity_key: entityKeys[0] ?? '', to_entity_key: entityKeys[1] ?? entityKeys[0] ?? '', relationship_type: 'many_to_one', join_type: 'inner', join_expression: '', description: '', metadata: {}, from_field: 'id', to_field: 'id' }); setOpen(true) }} addDisabled={readOnly} readOnly={readOnly} selectionMode={selectionMode} selectionBar={<SemanticSelectionBar entityLabel="relationships" selectedCount={selection.selectedCount} onDelete={() => void deleteSelected()} onCancel={() => selectionMode.exit()} />} page={list.page} pageSize={list.pageSize} total={list.total} onPageChange={list.setPage} onPageSizeChange={list.setPageSize}>
        <thead className="app-table-head"><tr>
          <SemanticAuthoringSelectHeader active={selectionMode.active} pageIds={list.items.map(r => r.id)} selection={selection} />
          <th className="px-3 py-2">From</th><th className="px-3 py-2">Relationship</th><th className="px-3 py-2">To</th><th className="px-3 py-2">Cardinality</th><th className="px-3 py-2">Join key</th><th className="px-3 py-2">Status</th>
          <th className="px-3 py-2"><SortableColumnHeader label="Modified" field="modified" activeField={list.sort} order={list.order} onSort={list.applySort} /></th>
          <th className="w-24 px-3 py-2">Actions</th>
        </tr></thead>
        <tbody>{list.items.map(r => (
          <tr key={r.id} className="h-11 border-b">
            <SemanticAuthoringSelectCell active={selectionMode.active} id={r.id} label={r.name} selection={selection} />
            <td className="px-3 py-2">{r.from_entity_key}</td><td className="px-3 py-2">{r.name}</td><td className="px-3 py-2">{r.to_entity_key}</td><td className="px-3 py-2">{r.relationship_type}</td><td className="px-3 py-2 font-mono text-xs">{r.join_expression}</td><td className="px-3 py-2 text-emerald-800">Ready</td><td className="px-3 py-2">{formatSemanticModified(r.modified_at)}</td>
            <td className="px-3 py-2"><RowActionsMenu label="Edit" items={[{ key: 'e', label: 'Edit', onClick: () => { setForm({ ...r, from_field: '', to_field: '' }); setBaseline(JSON.stringify(r)); setOpen(true) } }]} /></td>
          </tr>
        ))}</tbody>
      </SemanticAuthoringTableShell>
      <SemanticDrawer open={open && !!form} title="Relationship" onClose={() => setOpen(false)} onCancel={() => setOpen(false)} onSave={() => void handleSave()} saving={saving}>
        {form ? (<div className="grid gap-2 text-sm">
          <p>{form.from_entity_key} → {form.to_entity_key}</p>
          <input className="rounded border px-3 py-2" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Relationship name" />
          <select value={form.from_entity_key} onChange={e => setForm({ ...form, from_entity_key: e.target.value })}>{entityKeys.map(k => <option key={k}>{k}</option>)}</select>
          <input value={form.from_field} onChange={e => setForm({ ...form, from_field: e.target.value })} placeholder="From field" className="rounded border px-3 py-2" />
          <select value={form.to_entity_key} onChange={e => setForm({ ...form, to_entity_key: e.target.value })}>{entityKeys.map(k => <option key={k}>{k}</option>)}</select>
          <input value={form.to_field} onChange={e => setForm({ ...form, to_field: e.target.value })} placeholder="To field" className="rounded border px-3 py-2" />
          <select value={form.relationship_type} onChange={e => setForm({ ...form, relationship_type: e.target.value })}><option value="many_to_one">Many-to-one</option><option value="one_to_many">One-to-many</option></select>
          <textarea className="rounded border px-3 py-2" value={form.description ?? ''} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Business description" />
          <details><summary className="cursor-pointer text-xs text-slate-500">Advanced join expression</summary><input className="mt-1 w-full rounded border px-3 py-2 font-mono text-xs" value={form.join_expression} onChange={e => setForm({ ...form, join_expression: e.target.value })} /></details>
        </div>) : null}
      </SemanticDrawer>
    </>
  )
}

export function GlossaryTab({
  versionId,
  readOnly,
  entityKeys,
  onChanged,
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
          <tr key={t.id} className="h-11 border-b">
            <SemanticAuthoringSelectCell active={selectionMode.active} id={t.id} label={t.term} selection={selection} />
            <td className="px-3 py-2 font-medium">{t.term}</td><td className="px-3 py-2">{t.definition ?? '—'}</td><td className="px-3 py-2 text-xs">{t.synonyms.join(', ') || '—'}</td>
            <td className="px-3 py-2 text-xs">{[...t.related_metric_keys, ...t.related_dimension_keys].slice(0, 3).join(', ') || '—'}</td>
            <td className="px-3 py-2">{formatSemanticModified(t.modified_at)}</td>
            <td className="px-3 py-2"><RowActionsMenu label="Edit" items={[{ key: 'e', label: 'Edit', onClick: () => { setForm({ ...t, synonymsText: synonymsText(t.synonyms) }); setBaseline(JSON.stringify(t)); setOpen(true) } }]} /></td>
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
