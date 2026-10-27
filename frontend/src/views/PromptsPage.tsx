'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { MoreHorizontal, Plus, Search } from 'lucide-react'
import { EditorDrawer } from '../components/promptSkills/EditorDrawer'
import {
  PROMPT_SKILL_DEFAULT_PAGE_SIZE,
  PROMPT_SKILL_PAGE_SIZE_OPTIONS,
} from '../components/promptSkills/listTableConstants'
import { TablePagination } from '../components/knowledge/TablePagination'
import { TableHeaderCheckbox, TableRowCheckbox } from '../components/table/TableSelectionCheckbox'
import { TableSelectionActionBar } from '../components/table/TableSelectionActionBar'
import { PageCenter } from '../components/PageCenter'
import { useTableSelection } from '../lib/useTableSelection'
import { useTableSelectionMode } from '../lib/useTableSelectionMode'
import { ServiceErrorState } from '../components/ServiceErrorState'
import { api } from '../lib/api'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../lib/apiError'
import {
  formatModified,
  formatPromptKey,
  formatPromptVersionStatus,
  formatScope,
  slugRegistryKey,
} from '../lib/promptSkillDisplay'
import type { PromptRecord, PromptResolveResult, PromptVersionRecord } from '../types/api'

const KNOWN_KEYS = ['ask_data.system', 'rag.system', 'rag.insufficient_evidence'] as const
type PromptKey = (typeof KNOWN_KEYS)[number] | string

type DrawerTab = 'editor' | 'versions' | 'preview'
type SortKey = 'modified' | 'name'
type StatusFilter = '' | 'published' | 'draft'

type VersionSummary = { label: string; version: number | null; versions: PromptVersionRecord[] }

function RowMenu({
  onEdit,
  onPreview,
  onVersions,
  onDuplicate,
  onDelete,
}: {
  onEdit: () => void
  onPreview: () => void
  onVersions: () => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button type="button" aria-label="More actions" className="rounded-lg p-2 hover:bg-slate-100" onClick={() => setOpen(v => !v)}>
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open ? (
        <div className="absolute right-0 top-9 z-20 min-w-[10rem] rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {(
            [
              ['Edit', onEdit],
              ['Preview', onPreview],
              ['Versions', onVersions],
              ['Duplicate', onDuplicate],
              ['Delete', onDelete],
            ] as const
          ).map(([label, fn]) => (
            <button
              key={label}
              type="button"
              className={`block w-full px-3 py-2 text-left text-sm ${label === 'Delete' ? 'text-red-700 hover:bg-red-50' : 'text-slate-700 hover:bg-slate-50'}`}
              onClick={() => {
                setOpen(false)
                fn()
              }}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function PromptsPage() {
  const [prompts, setPrompts] = useState<PromptRecord[]>([])
  const [search, setSearch] = useState('')
  const [scopeFilter, setScopeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('')
  const [sortKey, setSortKey] = useState<SortKey>('modified')
  const [sortDesc, setSortDesc] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PROMPT_SKILL_DEFAULT_PAGE_SIZE)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<AppApiError | null>(null)
  const [error, setError] = useState('')

  const [versionMeta, setVersionMeta] = useState<Record<string, VersionSummary>>({})

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('edit')
  const [editorId, setEditorId] = useState<string | null>(null)
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('editor')

  const [editName, setEditName] = useState('')
  const [editKey, setEditKey] = useState<PromptKey>(KNOWN_KEYS[0])
  const [editScope, setEditScope] = useState<'global' | 'workspace' | 'project'>('global')
  const [editDescription, setEditDescription] = useState('')
  const [draftContent, setDraftContent] = useState('')
  const [versions, setVersions] = useState<PromptVersionRecord[]>([])
  const [dirty, setDirty] = useState(false)
  const [preview, setPreview] = useState<PromptResolveResult | null>(null)
  const [saving, setSaving] = useState(false)

  const listSelection = useTableSelection()
  const listSelectionMode = useTableSelectionMode(listSelection.clear)

  const editorPrompt = useMemo(
    () => (editorId ? prompts.find(p => p.id === editorId) ?? null : null),
    [editorId, prompts],
  )

  const refreshList = useCallback(async () => {
    const response = await api.listPrompts({
      search: search.trim() || undefined,
      scope: scopeFilter || undefined,
    })
    setPrompts(response.prompts)
  }, [search, scopeFilter])

  const loadVersionMeta = useCallback(async (promptId: string) => {
    try {
      const { versions: rows } = await api.listPromptVersions(promptId)
      const { label, version } = formatPromptVersionStatus(rows)
      setVersionMeta(prev => ({ ...prev, [promptId]: { label, version, versions: rows } }))
      return rows
    } catch {
      return []
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    refreshList()
      .catch(err => {
        setLoadError(toAppApiError(err))
        setError(safeErrorMessage(err, 'Failed to load prompts'))
      })
      .finally(() => setLoading(false))
  }, [refreshList])

  useEffect(() => {
    setPage(1)
  }, [search, scopeFilter, statusFilter, sortKey, sortDesc])

  const filteredSorted = useMemo(() => {
    let rows = [...prompts]
    if (statusFilter) {
      rows = rows.filter(p => {
        const label = versionMeta[p.id]?.label?.toLowerCase() ?? ''
        if (statusFilter === 'published') return label === 'published'
        if (statusFilter === 'draft') return label === 'draft'
        return true
      })
    }
    rows.sort((a, b) => {
      const dir = sortDesc ? -1 : 1
      if (sortKey === 'name') return dir * a.name.localeCompare(b.name)
      return dir * (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime())
    })
    return rows
  }, [prompts, statusFilter, versionMeta, sortKey, sortDesc])

  const paged = useMemo(() => {
    const start = (page - 1) * pageSize
    return filteredSorted.slice(start, start + pageSize)
  }, [filteredSorted, page, pageSize])

  useEffect(() => {
    paged.forEach(p => {
      if (!versionMeta[p.id]) void loadVersionMeta(p.id)
    })
  }, [paged, versionMeta, loadVersionMeta])

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(filteredSorted.length / pageSize) || 1)
    if (page > totalPages) setPage(totalPages)
  }, [filteredSorted.length, page, pageSize])

  function openCreateDrawer() {
    setDrawerMode('create')
    setEditorId(null)
    setEditName('')
    setEditKey(KNOWN_KEYS[0])
    setEditScope('global')
    setEditDescription('')
    setDraftContent('')
    setVersions([])
    setDirty(false)
    setPreview(null)
    setDrawerTab('editor')
    setDrawerOpen(true)
  }

  async function openEditDrawer(prompt: PromptRecord, tab: DrawerTab = 'editor') {
    setDrawerMode('edit')
    setEditorId(prompt.id)
    setEditName(prompt.name)
    setEditKey(prompt.key)
    setEditScope(prompt.scope)
    setEditDescription(prompt.description ?? '')
    setDirty(false)
    setPreview(null)
    setDrawerTab(tab)
    setDrawerOpen(true)
    const rows = versionMeta[prompt.id]?.versions ?? (await loadVersionMeta(prompt.id))
    setVersions(rows)
    const draft = rows.find(v => v.status === 'DRAFT')
    const active = rows.find(v => v.status === 'ACTIVE')
    const base = draft ?? active ?? rows[0]
    setDraftContent(base?.content ?? '')
    if (tab === 'preview') {
      api.resolvePrompt(prompt.key).then(setPreview).catch(err => setError(err instanceof Error ? err.message : 'Preview failed'))
    }
  }

  function closeDrawer() {
    setDrawerOpen(false)
    setEditorId(null)
    setDirty(false)
  }

  useEffect(() => {
    if (!drawerOpen || drawerTab !== 'preview' || !editorPrompt) return
    api.resolvePrompt(editorPrompt.key).then(setPreview).catch(err => setError(err instanceof Error ? err.message : 'Preview failed'))
  }, [drawerOpen, drawerTab, editorPrompt])

  async function handleSaveDraft() {
    setSaving(true)
    setError('')
    try {
      if (drawerMode === 'create') {
        if (!editName.trim()) {
          setError('Name is required')
          return
        }
        const { prompt } = await api.createPrompt({
          name: editName.trim(),
          key: editKey,
          scope: editScope,
          description: editDescription.trim() || undefined,
          initial_content: draftContent.trim() || `# ${editName.trim()}\n`,
        })
        setDrawerMode('edit')
        setEditorId(prompt.id)
        setDirty(false)
        await refreshList()
        await loadVersionMeta(prompt.id)
        const { versions: rows } = await api.listPromptVersions(prompt.id)
        setVersions(rows)
      } else if (editorId) {
        await api.createPromptVersion(editorId, { content: draftContent })
        setDirty(false)
        const rows = await loadVersionMeta(editorId)
        setVersions(rows)
        await refreshList()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function handlePublish(versionId: string) {
    if (!editorId) return
    setSaving(true)
    try {
      await api.publishPromptVersion(editorId, versionId)
      setDirty(false)
      const rows = await loadVersionMeta(editorId)
      setVersions(rows)
      await refreshList()
      if (drawerTab === 'preview' && editorPrompt) {
        await api.resolvePrompt(editorPrompt.key).then(setPreview)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setSaving(false)
    }
  }

  async function duplicatePrompt(record: PromptRecord) {
    setError('')
    try {
      const rows = versionMeta[record.id]?.versions ?? (await loadVersionMeta(record.id))
      const active = rows.find(v => v.status === 'ACTIVE') ?? rows[0]
      const suffix = Date.now().toString(36).slice(-4)
      const key = `${slugRegistryKey(record.name, 'prompt')}_copy_${suffix}`.slice(0, 64)
      await api.createPrompt({
        name: `${record.name} (copy)`,
        key,
        scope: record.scope,
        description: record.description ?? undefined,
        initial_content: active?.content ?? `# ${record.name}\n`,
      })
      await refreshList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Duplicate failed')
    }
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDesc(d => !d)
    else {
      setSortKey(key)
      setSortDesc(key === 'modified')
    }
  }

  if (loading && !prompts.length) {
    return (
      <PageCenter>
        <p className="text-sm text-slate-600">Loading prompts…</p>
      </PageCenter>
    )
  }

  if (loadError && !prompts.length) {
    return (
      <PageCenter>
        <ServiceErrorState
          title="Unable to load Prompts"
          message="We couldn't reach the backend service."
          error={loadError}
          onRetry={() => {
            setLoading(true)
            refreshList()
              .catch(err => setLoadError(toAppApiError(err)))
              .finally(() => setLoading(false))
          }}
        />
      </PageCenter>
    )
  }

  const drawerTitle = drawerMode === 'create' ? 'Create prompt' : editorPrompt?.name ?? 'Edit prompt'
  const drawerSubtitle =
    drawerMode === 'create'
      ? 'Save to register this prompt in the workspace.'
      : editorPrompt
        ? `Key: ${editorPrompt.key}${dirty ? ' · Unsaved changes' : ''}`
        : undefined

  return (
    <PageCenter className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="type-app-title text-xl">Prompts</h1>
          <p className="text-sm text-slate-600">Reusable instructions for AI behavior across your workspace.</p>
        </div>
        <button type="button" className="btn-primary inline-flex h-10 items-center gap-2 px-4 text-sm" onClick={openCreateDrawer}>
          <Plus className="h-4 w-4" />
          Create prompt
        </button>
      </div>

      {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div> : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-[200px] flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            className="w-full border-0 bg-transparent text-sm outline-none"
            placeholder="Search name or key…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            aria-label="Search prompts"
          />
        </div>
        <select className="app-select-filter" value={scopeFilter} onChange={e => setScopeFilter(e.target.value)}>
          <option value="">All scopes</option>
          <option value="global">Global</option>
          <option value="workspace">Workspace</option>
          <option value="project">Project</option>
        </select>
        <select className="app-select-filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value as StatusFilter)}>
          <option value="">All statuses</option>
          <option value="published">Published</option>
          <option value="draft">Draft</option>
        </select>
        <TableSelectionActionBar
          entityLabel="prompts"
          mode={listSelectionMode}
          selectedCount={listSelection.selectedCount}
        />
      </div>

      <div className="app-table-surface">
        <div className="app-table-surface-scroll">
          <table className="app-data-table min-w-[880px]">
            <thead className="app-table-head">
              <tr>
                {listSelectionMode.active ? (
                  <th className="w-11">
                    <TableHeaderCheckbox
                      state={listSelection.datasetCheckboxState(filteredSorted.length)}
                      onToggle={() =>
                        listSelection.toggleDatasetSelection(
                          filteredSorted.map(p => p.id),
                          filteredSorted.length,
                        )
                      }
                    />
                  </th>
                ) : null}
                <th>
                  <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort('name')}>
                    Name {sortKey === 'name' ? (sortDesc ? '↓' : '↑') : ''}
                  </button>
                </th>
                <th>Scope</th>
                <th>Key</th>
                <th>Status</th>
                <th>Version</th>
                <th>
                  <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort('modified')}>
                    Modified {sortKey === 'modified' ? (sortDesc ? '↓' : '↑') : ''}
                  </button>
                </th>
                <th className="w-24">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!paged.length ? (
                <tr>
                  <td colSpan={listSelectionMode.active ? 8 : 7} className="py-10 text-center text-slate-500">
                    No prompts yet. Create one to get started.
                  </td>
                </tr>
              ) : (
                paged.map(p => {
                  const meta = versionMeta[p.id]
                  return (
                    <tr key={p.id} className="border-t border-slate-100">
                      {listSelectionMode.active ? (
                        <td className="w-11">
                          <TableRowCheckbox
                            checked={listSelection.isSelected(p.id)}
                            label={`Select prompt ${p.name}`}
                            onToggle={() => listSelection.toggle(p.id)}
                          />
                        </td>
                      ) : null}
                      <td>
                        <button type="button" className="font-medium text-cloudera-navy hover:text-cloudera-violet" onClick={() => void openEditDrawer(p)}>
                          {p.name}
                        </button>
                      </td>
                      <td className="text-slate-600">{formatScope(p.scope)}</td>
                      <td className="font-mono text-slate-500">{p.key}</td>
                      <td>{meta?.label ?? '…'}</td>
                      <td>{meta?.version != null ? `v${meta.version}` : '—'}</td>
                      <td className="text-slate-600">{formatModified(p.updated_at)}</td>
                      <td>
                        <RowMenu
                          onEdit={() => void openEditDrawer(p)}
                          onPreview={() => void openEditDrawer(p, 'preview')}
                          onVersions={() => void openEditDrawer(p, 'versions')}
                          onDuplicate={() => void duplicatePrompt(p)}
                          onDelete={() => setError('Delete is not available via the API in this release.')}
                        />
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
        <TablePagination
          page={page}
          pageSize={pageSize}
          total={filteredSorted.length}
          onPageChange={setPage}
          onPageSizeChange={size => {
            setPageSize(size)
            setPage(1)
          }}
          pageSizeOptions={PROMPT_SKILL_PAGE_SIZE_OPTIONS}
        />
      </div>

      <EditorDrawer
        open={drawerOpen}
        title={drawerTitle}
        subtitle={drawerSubtitle}
        tabs={[
          { id: 'editor', label: 'Editor' },
          { id: 'versions', label: 'Versions' },
          { id: 'preview', label: 'Preview' },
        ]}
        activeTab={drawerTab}
        onTabChange={id => setDrawerTab(id as DrawerTab)}
        onClose={closeDrawer}
        footer={
          drawerTab === 'editor' ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-primary h-9 px-4 text-sm" disabled={saving || (drawerMode === 'edit' && !dirty && !editName.trim())} onClick={() => void handleSaveDraft()}>
                Save draft
              </button>
              <button
                type="button"
                className="h-9 rounded-lg border border-slate-200 px-4 text-sm font-semibold text-slate-700 disabled:opacity-50"
                disabled={saving || drawerMode === 'create'}
                onClick={() => {
                  const draft = versions.find(v => v.status === 'DRAFT')
                  if (draft) void handlePublish(draft.id)
                  else if (dirty) void handleSaveDraft()
                }}
              >
                Publish
              </button>
            </div>
          ) : null
        }
      >
        {drawerTab === 'editor' ? (
          <div className="space-y-3 text-sm">
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Display name</span>
              <input
                className="input mt-1 w-full"
                value={editName}
                disabled={drawerMode === 'edit'}
                onChange={e => {
                  setEditName(e.target.value)
                  setDirty(true)
                }}
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Internal key</span>
              {drawerMode === 'create' ? (
                <select className="input mt-1 w-full font-mono text-xs" value={editKey} onChange={e => setEditKey(e.target.value)}>
                  {KNOWN_KEYS.map(k => (
                    <option key={k} value={k}>
                      {k} ({formatPromptKey(k)})
                    </option>
                  ))}
                </select>
              ) : (
                <input className="input mt-1 w-full font-mono text-xs" value={editKey} readOnly />
              )}
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Scope</span>
              <select
                className="input mt-1 w-full"
                value={editScope}
                disabled={drawerMode === 'edit'}
                onChange={e => setEditScope(e.target.value as typeof editScope)}
              >
                <option value="global">Global</option>
                <option value="workspace">Workspace</option>
                <option value="project">Project</option>
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Prompt content</span>
              <textarea
                className="mt-1 min-h-[280px] w-full rounded-lg border border-slate-200 p-3 font-mono text-sm"
                value={draftContent}
                onChange={e => {
                  setDraftContent(e.target.value)
                  setDirty(true)
                }}
              />
            </label>
          </div>
        ) : null}

        {drawerTab === 'versions' ? (
          <div className="overflow-x-auto">
            <table className="app-data-table w-full">
              <thead className="app-table-head">
                <tr>
                  <th className="px-3 py-2">Version</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Modified</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {versions.map(v => (
                  <tr key={v.id} className="border-b border-slate-50">
                    <td className="px-3 py-2">v{v.version_number}</td>
                    <td className="px-3 py-2">{v.status === 'ACTIVE' ? 'Published' : v.status === 'DRAFT' ? 'Draft' : v.status}</td>
                    <td className="text-slate-500">{formatModified(v.created_at)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="text-xs font-semibold text-cloudera-violet"
                          onClick={() => {
                            setDraftContent(v.content)
                            setDrawerTab('editor')
                            setDirty(true)
                          }}
                        >
                          Open
                        </button>
                        {v.status === 'DRAFT' ? (
                          <button type="button" className="text-xs font-semibold text-emerald-700" onClick={() => void handlePublish(v.id)}>
                            Publish
                          </button>
                        ) : null}
                        {v.status === 'ARCHIVED' ? (
                          <button type="button" className="text-xs font-semibold text-slate-600" onClick={() => void handlePublish(v.id)}>
                            Rollback
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {drawerTab === 'preview' && preview ? (
          <div className="max-h-[min(70vh,520px)] space-y-3 overflow-y-auto text-sm">
            <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
              <div className="font-semibold text-cloudera-navy">Effective source: {preview.source_label}</div>
              <div className="mt-1 text-xs text-slate-600">Fallback chain: {(preview.chain ?? []).join(' → ')} → file</div>
              {editorPrompt ? (
                <div className="mt-2 text-xs text-slate-500">
                  Scope: {formatScope(editorPrompt.scope)} · Key: {editorPrompt.key}
                </div>
              ) : null}
            </div>
            <pre className="rounded-lg border border-slate-200 bg-white p-3 font-mono text-xs whitespace-pre-wrap">{preview.content}</pre>
          </div>
        ) : drawerTab === 'preview' ? (
          <p className="text-sm text-slate-500">Loading preview…</p>
        ) : null}
      </EditorDrawer>
    </PageCenter>
  )
}
