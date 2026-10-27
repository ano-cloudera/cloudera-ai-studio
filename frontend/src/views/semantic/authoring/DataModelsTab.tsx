'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { SortableColumnHeader } from '../../../components/table/SortableColumnHeader'
import { RowActionsMenu } from '../../../components/table/RowActionsMenu'
import { api } from '../../../lib/api'
import { setPendingChatContext, structuredContextSource } from '../../../lib/chatContext'
import type { ConnectorRecord, SemanticEntityImportPreview, SemanticEntityRecord } from '../../../types/api'
import { EntityConnectorSourceEditor } from '../EntityConnectorSourceEditor'
import { SemanticAuthoringTableShell } from './SemanticAuthoringTableShell'
import { SemanticDrawer } from './SemanticDrawer'
import { useEditorDirtyRegistry, useRegisterEditorDirty } from './EditorDirtyContext'
import {
  DATA_SOURCE_COLUMN,
  DATA_SOURCE_REQUIRED,
  OPEN_DATA_SOURCE,
} from '../../connectors/dataSourceUx'
import { entityConnectorLabel, entityFieldCount, formatSemanticModified, physicalSource, semanticKeyFromName } from './semanticFormat'
import { useSemanticPaginatedList } from './useSemanticPaginatedList'
import { SemanticAuthoringSelectCell, SemanticAuthoringSelectHeader } from './SemanticAuthoringSelectionCells'
import { SemanticSelectionBar, useSemanticAuthoringSelection, useSemanticBulkDeleteAction } from './useSemanticAuthoringSelection'

type Props = {
  versionId: string | null
  readOnly: boolean
  connectors: ConnectorRecord[]
  onChanged: () => void
  onEntityImported?: (ctx: { connectionId: string; qualified: string }) => void
}

type DrawerMode = 'create' | 'edit' | null

export function DataModelsTab({ versionId, readOnly, connectors, onChanged, onEntityImported }: Props) {
  const router = useRouter()
  const fetchPage = useCallback(async (vid: string, params: Parameters<typeof api.listSemanticEntities>[1]) => {
    const r = await api.listSemanticEntities(vid, params)
    return {
      items: r.entities,
      meta: r.total != null ? { total: r.total, page: r.page ?? 1, page_size: r.page_size ?? r.entities.length } : undefined,
    }
  }, [])
  const list = useSemanticPaginatedList(versionId, fetchPage)
  const { selection, mode: selectionMode } = useSemanticAuthoringSelection()
  const deleteSelected = useSemanticBulkDeleteAction(
    versionId,
    (vid, ids) => api.bulkDeleteSemanticEntities(vid, { ids }),
    async () => {
      await list.reload()
      onChanged()
    },
    selection,
    selectionMode,
  )
  useEffect(() => {
    selection.clear()
  }, [list.search, list.page, list.pageSize, list.sort, list.order, selection.clear])
  const [drawer, setDrawer] = useState<DrawerMode>(null)
  const [form, setForm] = useState<SemanticEntityRecord | null>(null)
  const [baseline, setBaseline] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [importPreview, setImportPreview] = useState<SemanticEntityImportPreview | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  function closeDrawer() {
    setDrawer(null)
    setForm(null)
    setErrors([])
    setImportPreview(null)
  }

  function openCreate() {
    setForm({
      id: '',
      key: '',
      name: '',
      description: '',
      source_type: 'logical',
      catalog: null,
      schema: null,
      table_name: null,
      view_name: null,
      primary_key: null,
      connection_id: null,
      metadata: {},
    })
    setBaseline(JSON.stringify({
      id: '',
      key: '',
      name: '',
      description: '',
      source_type: 'logical',
      catalog: null,
      schema: null,
      table_name: null,
      view_name: null,
      primary_key: null,
      connection_id: null,
      metadata: {},
    }))
    setDrawer('create')
  }

  function openEdit(entity: SemanticEntityRecord) {
    setForm({ ...entity })
    setBaseline(JSON.stringify(entity))
    setDrawer('edit')
  }

  const handleSave = useCallback(async () => {
    if (!form || !versionId) return
    const nextErrors: string[] = []
    if (!form.name.trim()) nextErrors.push('Name is required.')
    if (drawer === 'create' && !form.connection_id) nextErrors.push(DATA_SOURCE_REQUIRED)
    if (drawer === 'create' && !form.schema) nextErrors.push('Schema is required.')
    if (drawer === 'create' && !form.table_name) nextErrors.push('Physical table is required.')
    if (nextErrors.length) {
      setErrors(nextErrors)
      throw new Error('validation')
    }
    setSaving(true)
    setErrors([])
    try {
      if (drawer === 'create') {
        const key = semanticKeyFromName(form.name)
        await api.importSemanticEntity(versionId, {
          connector_id: form.connection_id!,
          catalog: form.catalog,
          schema: form.schema,
          table: form.table_name!,
          name: form.name.trim(),
          key,
          description: form.description,
        })
        const qualified = [form.catalog, form.schema, form.table_name].filter(Boolean).join('.')
        onEntityImported?.({ connectionId: form.connection_id!, qualified })
      } else {
        await api.patchSemanticEntity(versionId, form.id, {
          name: form.name,
          description: form.description,
          primary_key: form.primary_key,
          catalog: form.catalog,
          db_schema: form.schema,
          table_name: form.table_name,
          connection_id: form.connection_id,
          metadata: form.metadata,
        })
      }
      closeDrawer()
      await list.reload()
      onChanged()
    } catch (err) {
      setErrors([err instanceof Error ? err.message : 'Save failed'])
      throw err
    } finally {
      setSaving(false)
    }
  }, [drawer, form, versionId, list, onChanged])

  const registration = useMemo(
    () =>
      drawer && form
        ? {
            isDirty: () => JSON.stringify(form) !== baseline,
            save: handleSave,
            discard: closeDrawer,
          }
        : null,
    [drawer, form, baseline, handleSave],
  )
  useRegisterEditorDirty(registration)

  async function handleDelete(entity: SemanticEntityRecord) {
    if (!versionId || readOnly) return
    await api.deleteSemanticEntity(versionId, entity.id)
    await list.reload()
    onChanged()
  }

  function askThisData(entity: SemanticEntityRecord) {
    setPendingChatContext([
      structuredContextSource({ type: 'semantic_entity', id: entity.id, name: entity.name }),
    ])
    router.push('/')
  }

  useEffect(() => {
    if (!form?.connection_id || !form.schema || !form.table_name || drawer !== 'create' || !versionId) {
      setImportPreview(null)
      return
    }
    api
      .previewSemanticEntityImport(versionId, {
        connector_id: form.connection_id,
        catalog: form.catalog,
        schema: form.schema,
        table: form.table_name,
      })
      .then(r => setImportPreview(r.preview))
      .catch(() => setImportPreview(null))
  }, [form?.connection_id, form?.schema, form?.table_name, drawer, versionId])

  const colSpan = selectionMode.active ? 9 : 8

  return (
    <>
      <SemanticAuthoringTableShell
        testId="semantic-data-models-table"
        searchPlaceholder="Search data models…"
        search={list.search}
        onSearchChange={list.setSearch}
        loading={list.loading}
        error={list.error}
        onRetry={() => void list.reload()}
        emptyMessage="No data models yet. Add a data model to map business objects to connected tables."
        emptyColSpan={colSpan}
        hasRows={list.items.length > 0}
        addLabel="+ Add data model"
        onAdd={openCreate}
        addDisabled={readOnly}
        readOnly={readOnly}
        selectionMode={selectionMode}
        selectionBar={
          <SemanticSelectionBar
            entityLabel="data models"
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
            <SemanticAuthoringSelectHeader active={selectionMode.active} pageIds={list.items.map(e => e.id)} selection={selection} />
            <th className="px-3 py-2">
              <SortableColumnHeader label="Name" field="name" activeField={list.sort} order={list.order} onSort={list.applySort} />
            </th>
            <th className="px-3 py-2">Business definition</th>
            <th className="px-3 py-2">Primary source</th>
            <th className="px-3 py-2">{DATA_SOURCE_COLUMN}</th>
            <th className="w-16 px-3 py-2">Fields</th>
            <th className="w-24 px-3 py-2">Status</th>
            <th className="px-3 py-2">
              <SortableColumnHeader label="Modified" field="modified" activeField={list.sort} order={list.order} onSort={list.applySort} />
            </th>
            <th className="w-24 px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {list.items.map(entity => (
            <tr key={entity.id} className="h-11 border-b border-slate-50 hover:bg-slate-50/60">
              <SemanticAuthoringSelectCell active={selectionMode.active} id={entity.id} label={entity.name} selection={selection} />
              <td className="truncate px-3 py-2 font-medium text-cloudera-navy">{entity.name}</td>
              <td className="truncate px-3 py-2 text-slate-600">{entity.description ?? '—'}</td>
              <td className="truncate font-mono text-slate-600">{physicalSource(entity)}</td>
              <td className="truncate px-3 py-2 text-slate-600">{entityConnectorLabel(entity, connectors)}</td>
              <td className="px-3 py-2 text-slate-600">{entityFieldCount(entity)}</td>
              <td className="font-semibold text-emerald-800">Ready</td>
              <td className="px-3 py-2 text-slate-600">{formatSemanticModified(entity.modified_at)}</td>
              <td className="px-3 py-2">
                <RowActionsMenu
                  label={`Actions for ${entity.name}`}
                  items={[
                    { key: 'edit', label: 'Edit', onClick: () => openEdit(entity) },
                    {
                      key: 'preview',
                      label: 'Preview data',
                      onClick: () => {
                        setPreviewOpen(true)
                        setForm(entity)
                      },
                    },
                    { key: 'ask', label: 'Ask this data', onClick: () => askThisData(entity) },
                    { key: 'sep', separator: true },
                    { key: 'delete', label: 'Delete', danger: true, onClick: () => void handleDelete(entity) },
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </SemanticAuthoringTableShell>

      <SemanticDrawer
        open={drawer != null && form != null}
        title={drawer === 'create' ? 'Add data model' : 'Edit data model'}
        onClose={closeDrawer}
        onCancel={closeDrawer}
        onSave={() => void handleSave()}
        saving={saving}
        errors={errors}
      >
        {form ? (
          <div className="grid gap-3">
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Business model name</span>
              <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Business definition</span>
              <textarea className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" rows={2} value={form.description ?? ''} onChange={e => setForm({ ...form, description: e.target.value })} />
            </label>
            {drawer === 'create' ? (
              <>
                <EntityConnectorSourceEditor
                  entity={form}
                  readOnly={false}
                  form={form}
                  setForm={updater => setForm(prev => (prev ? (typeof updater === 'function' ? updater(prev) : updater) : prev))}
                  onDirty={() => undefined}
                />
                {importPreview?.existing_entity ? (
                  <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                    Table already mapped to {importPreview.existing_entity.name}. Saving may duplicate unless allowed.
                  </p>
                ) : null}
              </>
            ) : (
              <EntityConnectorSourceEditor
                entity={form}
                readOnly={readOnly}
                form={form}
                setForm={updater => setForm(prev => (prev ? (typeof updater === 'function' ? updater(prev) : updater) : prev))}
                onDirty={() => undefined}
              />
            )}
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Primary key</span>
              <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" value={form.primary_key ?? ''} onChange={e => setForm({ ...form, primary_key: e.target.value })} />
            </label>
          </div>
        ) : null}
      </SemanticDrawer>

      {previewOpen && form ? (
        <SemanticDrawer open footer="close-only" title={`Preview — ${form.name}`} onClose={() => setPreviewOpen(false)} onCancel={() => setPreviewOpen(false)} onSave={() => setPreviewOpen(false)}>
          <p className="text-sm text-slate-600">Physical source: {physicalSource(form)}</p>
          {form.connection_id ? (
            <button type="button" className="mt-3 text-sm font-semibold text-cloudera-violet underline" onClick={() => router.push(`/connectors/${form.connection_id}`)}>
              {OPEN_DATA_SOURCE}
            </button>
          ) : null}
        </SemanticDrawer>
      ) : null}
    </>
  )
}
