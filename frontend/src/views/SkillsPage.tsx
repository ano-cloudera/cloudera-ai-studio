'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { MoreHorizontal, Plus, Search } from 'lucide-react'
import { EditorDrawer } from '../components/promptSkills/EditorDrawer'
import {
  PROMPT_SKILL_DEFAULT_PAGE_SIZE,
  PROMPT_SKILL_PAGE_SIZE_OPTIONS,
} from '../components/promptSkills/listTableConstants'
import { TablePagination } from '../components/knowledge/TablePagination'
import { PageCenter } from '../components/PageCenter'
import { ServiceErrorState } from '../components/ServiceErrorState'
import { api } from '../lib/api'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../lib/apiError'
import {
  formatHandlerType,
  formatModified,
  formatPromptKey,
  formatScope,
  formatSkillListStatus,
  formatToolName,
  slugRegistryKey,
} from '../lib/promptSkillDisplay'
import type { SkillExecuteResult, SkillRecord, SkillToolRecord, SkillVersionRecord } from '../types/api'

const HANDLER_TYPES = ['prompt_only', 'rag', 'ask_data'] as const
const PROMPT_KEYS = ['', 'ask_data.system', 'rag.system', 'rag.insufficient_evidence']

type DrawerTab = 'configuration' | 'versions' | 'test'
type SortKey = 'modified' | 'name'

type SkillVersionSummary = {
  handler: string
  promptKey: string
  toolCount: number
  versions: SkillVersionRecord[]
}

function RowMenu({
  onEdit,
  onTest,
  onVersions,
  onDuplicate,
  onDelete,
}: {
  onEdit: () => void
  onTest: () => void
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
              ['Test', onTest],
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

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [tools, setTools] = useState<SkillToolRecord[]>([])
  const [search, setSearch] = useState('')
  const [scopeFilter, setScopeFilter] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('modified')
  const [sortDesc, setSortDesc] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PROMPT_SKILL_DEFAULT_PAGE_SIZE)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<AppApiError | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const [versionMeta, setVersionMeta] = useState<Record<string, SkillVersionSummary>>({})

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('edit')
  const [editorId, setEditorId] = useState<string | null>(null)
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('configuration')

  const [editName, setEditName] = useState('')
  const [editKey, setEditKey] = useState('')
  const [editScope, setEditScope] = useState<'workspace' | 'project'>('workspace')
  const [instructions, setInstructions] = useState('')
  const [promptKey, setPromptKey] = useState('')
  const [handlerType, setHandlerType] = useState<(typeof HANDLER_TYPES)[number]>('prompt_only')
  const [allowedTools, setAllowedTools] = useState<string[]>([])
  const [inputSchemaText, setInputSchemaText] = useState('')
  const [versions, setVersions] = useState<SkillVersionRecord[]>([])

  const [testInput, setTestInput] = useState('')
  const [testResult, setTestResult] = useState<SkillExecuteResult | null>(null)
  const [testRunning, setTestRunning] = useState(false)

  const editorSkill = useMemo(() => (editorId ? skills.find(s => s.id === editorId) ?? null : null), [editorId, skills])

  const refreshList = useCallback(async () => {
    const response = await api.listSkills({ search: search.trim() || undefined, scope: scopeFilter || undefined })
    setSkills(response.skills)
  }, [search, scopeFilter])

  const loadTools = useCallback(async () => {
    const response = await api.listTools()
    setTools(response.tools)
  }, [])

  const loadVersionMeta = useCallback(async (skillId: string) => {
    try {
      const { versions: rows } = await api.listSkillVersions(skillId)
      const draft = rows.find(v => v.status === 'DRAFT')
      const active = rows.find(v => v.status === 'ACTIVE')
      const base = draft ?? active ?? rows[0]
      const handler = String(base?.config?.handler_type ?? '')
      setVersionMeta(prev => ({
        ...prev,
        [skillId]: {
          handler,
          promptKey: base?.prompt_key ?? '',
          toolCount: base?.allowed_tools?.length ?? 0,
          versions: rows,
        },
      }))
      return rows
    } catch {
      return []
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    Promise.all([refreshList(), loadTools()])
      .catch(err => {
        setLoadError(toAppApiError(err))
        setError(safeErrorMessage(err, 'Failed to load'))
      })
      .finally(() => setLoading(false))
  }, [refreshList, loadTools])

  useEffect(() => {
    setPage(1)
  }, [search, scopeFilter, sortKey, sortDesc])

  const filteredSorted = useMemo(() => {
    const rows = [...skills]
    rows.sort((a, b) => {
      const dir = sortDesc ? -1 : 1
      if (sortKey === 'name') return dir * a.name.localeCompare(b.name)
      return dir * (new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime())
    })
    return rows
  }, [skills, sortKey, sortDesc])

  const paged = useMemo(() => {
    const start = (page - 1) * pageSize
    return filteredSorted.slice(start, start + pageSize)
  }, [filteredSorted, page, pageSize])

  useEffect(() => {
    paged.forEach(s => {
      if (!versionMeta[s.id]) void loadVersionMeta(s.id)
    })
  }, [paged, versionMeta, loadVersionMeta])

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(filteredSorted.length / pageSize) || 1)
    if (page > totalPages) setPage(totalPages)
  }, [filteredSorted.length, page, pageSize])

  function applyVersionToForm(rows: SkillVersionRecord[]) {
    const draft = rows.find(v => v.status === 'DRAFT')
    const active = rows.find(v => v.status === 'ACTIVE')
    const base = draft ?? active ?? rows[0]
    if (!base) return
    setInstructions(base.instructions)
    setPromptKey(base.prompt_key ?? '')
    setHandlerType((base.config?.handler_type as typeof handlerType) || 'prompt_only')
    setAllowedTools(base.allowed_tools ?? [])
    setInputSchemaText(base.input_schema ? JSON.stringify(base.input_schema, null, 2) : '')
  }

  function openCreateDrawer() {
    setDrawerMode('create')
    setEditorId(null)
    setEditName('')
    setEditKey('')
    setEditScope('workspace')
    setInstructions('')
    setPromptKey('')
    setHandlerType('prompt_only')
    setAllowedTools([])
    setInputSchemaText('')
    setVersions([])
    setDirty(false)
    setTestResult(null)
    setDrawerTab('configuration')
    setDrawerOpen(true)
  }

  async function openEditDrawer(skill: SkillRecord, tab: DrawerTab = 'configuration') {
    setDrawerMode('edit')
    setEditorId(skill.id)
    setEditName(skill.name)
    setEditKey(skill.key)
    setEditScope(skill.scope)
    setDirty(false)
    setTestResult(null)
    setDrawerTab(tab)
    setDrawerOpen(true)
    const rows = versionMeta[skill.id]?.versions ?? (await loadVersionMeta(skill.id))
    setVersions(rows)
    applyVersionToForm(rows)
  }

  function closeDrawer() {
    setDrawerOpen(false)
    setEditorId(null)
    setDirty(false)
  }

  function toggleTool(key: string) {
    setAllowedTools(current => (current.includes(key) ? current.filter(k => k !== key) : [...current, key]))
    setDirty(true)
  }

  async function saveDraft() {
    setSaving(true)
    setError('')
    let input_schema: Record<string, unknown> | undefined
    if (inputSchemaText.trim()) {
      try {
        input_schema = JSON.parse(inputSchemaText) as Record<string, unknown>
      } catch {
        setError('Input schema must be valid JSON')
        setSaving(false)
        return
      }
    }
    try {
      if (drawerMode === 'create') {
        if (!editName.trim()) {
          setError('Name is required')
          return
        }
        const key = editKey.trim() || slugRegistryKey(editName, 'skill')
        const { skill } = await api.createSkill({
          name: editName.trim(),
          key,
          scope: editScope,
          instructions,
          allowed_tools: allowedTools,
          config: { handler_type: handlerType },
          prompt_key: promptKey || undefined,
        })
        setDrawerMode('edit')
        setEditorId(skill.id)
        setEditKey(skill.key)
        setDirty(false)
        await refreshList()
        const rows = await loadVersionMeta(skill.id)
        setVersions(rows)
      } else if (editorId) {
        await api.createSkillVersion(editorId, {
          instructions,
          prompt_key: promptKey || undefined,
          allowed_tools: allowedTools,
          input_schema,
          config: { handler_type: handlerType },
        })
        setDirty(false)
        const rows = await loadVersionMeta(editorId)
        setVersions(rows)
        applyVersionToForm(rows)
        await refreshList()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function publishVersion(versionId: string) {
    if (!editorId) return
    setSaving(true)
    try {
      await api.publishSkillVersion(editorId, versionId)
      setDirty(false)
      const rows = await loadVersionMeta(editorId)
      setVersions(rows)
      await refreshList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setSaving(false)
    }
  }

  async function runTest() {
    if (!editorId || !testInput.trim()) return
    setTestRunning(true)
    setError('')
    setTestResult(null)
    try {
      const result = await api.executeSkill(editorId, { input: testInput.trim() })
      setTestResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Execution failed')
    } finally {
      setTestRunning(false)
    }
  }

  async function duplicateSkill(record: SkillRecord) {
    setError('')
    try {
      const rows = versionMeta[record.id]?.versions ?? (await loadVersionMeta(record.id))
      const active = rows.find(v => v.status === 'ACTIVE') ?? rows[0]
      const suffix = Date.now().toString(36).slice(-4)
      await api.createSkill({
        name: `${record.name} (copy)`,
        key: `${slugRegistryKey(record.name, 'skill')}_copy_${suffix}`.slice(0, 64),
        scope: record.scope,
        instructions: active?.instructions ?? '',
        allowed_tools: active?.allowed_tools ?? [],
        config: active?.config ?? { handler_type: 'prompt_only' },
        prompt_key: active?.prompt_key ?? undefined,
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

  if (loading && !skills.length) {
    return (
      <PageCenter>
        <p className="text-sm text-slate-600">Loading skills…</p>
      </PageCenter>
    )
  }

  if (loadError && !skills.length) {
    return (
      <PageCenter>
        <ServiceErrorState
          title="Unable to load Skills"
          message="We couldn't reach the backend service."
          error={loadError}
          onRetry={() => {
            setLoading(true)
            Promise.all([refreshList(), loadTools()])
              .catch(err => setLoadError(toAppApiError(err)))
              .finally(() => setLoading(false))
          }}
        />
      </PageCenter>
    )
  }

  const drawerTitle = drawerMode === 'create' ? 'New skill' : editorSkill?.name ?? 'Edit skill'
  const drawerSubtitle =
    drawerMode === 'create'
      ? 'Save draft to register this skill.'
      : editorSkill
        ? `Key: ${editorSkill.key}${dirty ? ' · Unsaved changes' : ''}`
        : undefined

  return (
    <PageCenter className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="type-app-title text-xl">Skills</h1>
          <p className="text-sm text-slate-600">Reusable AI capabilities combining prompts and approved tools.</p>
        </div>
        <button type="button" className="btn-primary inline-flex h-10 items-center gap-2 px-4 text-sm" onClick={openCreateDrawer}>
          <Plus className="h-4 w-4" />
          New skill
        </button>
      </div>

      {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div> : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-[200px] flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
          <Search className="h-4 w-4 text-slate-400" />
          <input className="w-full border-0 bg-transparent text-sm outline-none" placeholder="Search skills…" value={search} onChange={e => setSearch(e.target.value)} aria-label="Search skills" />
        </div>
        <select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" value={scopeFilter} onChange={e => setScopeFilter(e.target.value)}>
          <option value="">All scopes</option>
          <option value="workspace">Workspace</option>
          <option value="project">Project</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-[960px] w-full text-left text-sm">
            <thead className="app-table-head">
              <tr>
                <th className="px-4 py-3">
                  <button type="button" onClick={() => toggleSort('name')}>
                    Name {sortKey === 'name' ? (sortDesc ? '↓' : '↑') : ''}
                  </button>
                </th>
                <th className="px-4 py-3">Handler</th>
                <th className="px-4 py-3">Scope</th>
                <th className="px-4 py-3">Prompt</th>
                <th className="px-4 py-3">Tools</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">
                  <button type="button" onClick={() => toggleSort('modified')}>
                    Modified {sortKey === 'modified' ? (sortDesc ? '↓' : '↑') : ''}
                  </button>
                </th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!paged.length ? (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-slate-500">
                    No skills yet. Create one to get started.
                  </td>
                </tr>
              ) : (
                paged.map(s => {
                  const meta = versionMeta[s.id]
                  return (
                    <tr key={s.id} className="border-t border-slate-100">
                      <td className="px-4 py-3">
                        <button type="button" className="font-medium text-cloudera-navy hover:text-cloudera-violet" onClick={() => void openEditDrawer(s)}>
                          {s.name}
                        </button>
                      </td>
                      <td className="px-4 py-3">{meta ? formatHandlerType(meta.handler) : '…'}</td>
                      <td className="px-4 py-3">{formatScope(s.scope)}</td>
                      <td className="px-4 py-3 text-slate-600">{meta ? formatPromptKey(meta.promptKey) : '…'}</td>
                      <td className="px-4 py-3">{meta ? `${meta.toolCount} tool${meta.toolCount === 1 ? '' : 's'}` : '…'}</td>
                      <td className="px-4 py-3">{formatSkillListStatus(s.status)}</td>
                      <td className="px-4 py-3 text-slate-600">{formatModified(s.updated_at)}</td>
                      <td className="px-4 py-3">
                        <RowMenu
                          onEdit={() => void openEditDrawer(s)}
                          onTest={() => void openEditDrawer(s, 'test')}
                          onVersions={() => void openEditDrawer(s, 'versions')}
                          onDuplicate={() => void duplicateSkill(s)}
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
          { id: 'configuration', label: 'Configuration' },
          { id: 'versions', label: 'Versions' },
          { id: 'test', label: 'Test' },
        ]}
        activeTab={drawerTab}
        onTabChange={id => setDrawerTab(id as DrawerTab)}
        onClose={closeDrawer}
        footer={
          drawerTab === 'configuration' ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-primary h-9 px-4 text-sm" disabled={saving || (drawerMode === 'edit' && !dirty && !editName.trim())} onClick={() => void saveDraft()}>
                Save draft
              </button>
              <button
                type="button"
                className="h-9 rounded-lg border border-slate-200 px-4 text-sm font-semibold disabled:opacity-50"
                disabled={saving || drawerMode === 'create'}
                onClick={() => {
                  const draft = versions.find(v => v.status === 'DRAFT')
                  if (draft) void publishVersion(draft.id)
                }}
              >
                Publish latest draft
              </button>
            </div>
          ) : null
        }
      >
        {drawerTab === 'configuration' ? (
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
              <input
                className="input mt-1 w-full font-mono text-xs"
                value={editKey}
                readOnly={drawerMode === 'edit'}
                placeholder="ask_data_analyst"
                onChange={e => {
                  setEditKey(e.target.value)
                  setDirty(true)
                }}
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Scope</span>
              <select className="input mt-1 w-full" value={editScope} disabled={drawerMode === 'edit'} onChange={e => setEditScope(e.target.value as typeof editScope)}>
                <option value="workspace">Workspace</option>
                <option value="project">Project</option>
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Handler type</span>
              <select
                className="input mt-1 w-full"
                value={handlerType}
                onChange={e => {
                  setHandlerType(e.target.value as typeof handlerType)
                  setDirty(true)
                }}
              >
                {HANDLER_TYPES.map(h => (
                  <option key={h} value={h}>
                    {formatHandlerType(h)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Prompt reference</span>
              <select
                className="input mt-1 w-full"
                value={promptKey}
                onChange={e => {
                  setPromptKey(e.target.value)
                  setDirty(true)
                }}
              >
                {PROMPT_KEYS.map(k => (
                  <option key={k || 'none'} value={k}>
                    {formatPromptKey(k)}
                  </option>
                ))}
              </select>
            </label>
            <div>
              <span className="text-xs font-semibold text-slate-600">Allowed tools</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {tools.map(tool => {
                  const on = allowedTools.includes(tool.key)
                  return (
                    <button
                      key={tool.key}
                      type="button"
                      onClick={() => toggleTool(tool.key)}
                      className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                        on ? 'border-cloudera-violet bg-violet-50 text-cloudera-violet' : 'border-slate-200 text-slate-600'
                      }`}
                    >
                      {on ? '✓ ' : ''}
                      {formatToolName(tool.key)}
                    </button>
                  )
                })}
              </div>
            </div>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Instructions</span>
              <textarea
                className="mt-1 min-h-[140px] w-full rounded-lg border border-slate-200 p-3 font-mono text-xs"
                value={instructions}
                onChange={e => {
                  setInstructions(e.target.value)
                  setDirty(true)
                }}
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Input schema (JSON, optional)</span>
              <textarea
                className="mt-1 min-h-[80px] w-full rounded-lg border border-slate-200 p-3 font-mono text-xs"
                value={inputSchemaText}
                onChange={e => {
                  setInputSchemaText(e.target.value)
                  setDirty(true)
                }}
              />
            </label>
          </div>
        ) : null}

        {drawerTab === 'versions' ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="app-table-head">
                <tr>
                  <th className="px-3 py-2">Version</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Published</th>
                  <th className="px-3 py-2">Modified</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {versions.map(v => (
                  <tr key={v.id} className="border-b border-slate-50">
                    <td className="px-3 py-2">v{v.version_number}</td>
                    <td className="px-3 py-2">{v.status === 'ACTIVE' ? 'Published' : v.status === 'DRAFT' ? 'Draft' : v.status}</td>
                    <td className="px-3 py-2 text-xs">{v.status === 'ACTIVE' ? 'Yes' : '—'}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{formatModified(v.created_at)}</td>
                    <td className="px-3 py-2">
                      {v.status === 'DRAFT' ? (
                        <button type="button" className="text-xs font-semibold text-emerald-700" onClick={() => void publishVersion(v.id)}>
                          Publish
                        </button>
                      ) : null}
                      {v.status === 'ARCHIVED' ? (
                        <button type="button" className="text-xs font-semibold text-slate-600" onClick={() => void publishVersion(v.id)}>
                          Rollback
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {drawerTab === 'test' ? (
          <div className="space-y-3 text-sm">
            {drawerMode === 'create' ? (
              <p className="text-slate-600">Save the skill as a draft before running a test.</p>
            ) : (
              <>
                <textarea className="min-h-[100px] w-full rounded-lg border border-slate-200 p-3" placeholder="Test input" value={testInput} onChange={e => setTestInput(e.target.value)} />
                <button type="button" className="btn-primary h-9 px-4 text-sm" disabled={testRunning} onClick={() => void runTest()}>
                  {testRunning ? 'Running…' : 'Run skill'}
                </button>
                {testResult ? (
                  <div className="max-h-[360px] overflow-y-auto rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs">
                    <div>Handler: {formatHandlerType(testResult.execution.handler_type)}</div>
                    <div>Prompt source: {testResult.execution.prompt_source ?? 'n/a'}</div>
                    <div>Tools: {(testResult.execution.tools_used ?? []).map(formatToolName).join(', ') || 'none'}</div>
                    <div>Time: {testResult.execution.execution_ms} ms</div>
                    <pre className="mt-2 whitespace-pre-wrap">{JSON.stringify(testResult.result, null, 2)}</pre>
                  </div>
                ) : null}
              </>
            )}
          </div>
        ) : null}
      </EditorDrawer>
    </PageCenter>
  )
}
