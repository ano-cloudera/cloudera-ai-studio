'use client'

import { useCallback, useEffect, useState } from 'react'
import { Pencil, Plug, Plus, Trash2 } from 'lucide-react'
import { api } from '../../lib/api'
import { safeErrorMessage, toAppApiError, type AppApiError } from '../../lib/apiError'
import type {
  McpServerEntryPayload,
  McpTestConnectionResult,
  McpWorkspaceSettingsPayload,
} from '../../types/api'

const BRAVE_PRESET: McpServerEntryPayload = {
  id: '',
  name: 'Brave Search MCP',
  description: 'Web search via @modelcontextprotocol/server-brave-search (set BRAVE_API_KEY on backend).',
  enabled: true,
  transport: 'stdio',
  command: 'npx',
  args: ['-y', '@modelcontextprotocol/server-brave-search'],
  env_var_names: ['BRAVE_API_KEY'],
  url: null,
  header_env_var_names: {},
  default_tool: null,
}

function emptyServer(): McpServerEntryPayload {
  return {
    id: crypto.randomUUID(),
    name: '',
    description: '',
    enabled: true,
    transport: 'stdio',
    command: 'npx',
    args: [],
    env_var_names: [],
    url: null,
    header_env_var_names: {},
    default_tool: null,
  }
}

function normalized(server: McpServerEntryPayload): McpServerEntryPayload {
  return {
    ...server,
    name: server.name.trim(),
    command: server.transport === 'stdio' ? (server.command || '').trim() || null : null,
    url: server.transport === 'sse' ? (server.url || '').trim() || null : null,
  }
}

function canTest(server: McpServerEntryPayload): boolean {
  if (!server.name.trim()) return false
  if (server.transport === 'stdio') return !!(server.command || '').trim()
  return !!(server.url || '').trim()
}

type Props = {
  embedded?: boolean
}

type TestResult = { ok: boolean; message: string }

export function AskDataMcpSettingsPanel({ embedded = false }: Props) {
  const [draft, setDraft] = useState<McpWorkspaceSettingsPayload>({ servers: [] })
  const [saved, setSaved] = useState<McpWorkspaceSettingsPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<AppApiError | null>(null)
  const [banner, setBanner] = useState('')
  const [editingIds, setEditingIds] = useState<Set<string>>(new Set())
  const [testingId, setTestingId] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, TestResult>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getMcpSettings()
      setDraft(response.settings)
      setSaved(response.settings)
    } catch (e) {
      setError(toAppApiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const savedIds = new Set((saved?.servers ?? []).map(s => s.id))
  // A server that was never saved is always in edit mode; a saved one is read-only until Edit is pressed.
  const isEditing = (server: McpServerEntryPayload) => editingIds.has(server.id) || !savedIds.has(server.id)

  function stopEditing(id: string) {
    setEditingIds(ids => {
      const copy = new Set(ids)
      copy.delete(id)
      return copy
    })
  }

  async function persist(servers: McpServerEntryPayload[], message: string): Promise<boolean> {
    setSaving(true)
    setBanner('')
    setError(null)
    try {
      const response = await api.putMcpSettings({ servers: servers.filter(s => s.name.trim()) })
      setSaved(response.settings)
      setDraft(response.settings)
      setBanner(message)
      return true
    } catch (e) {
      setError(toAppApiError(e))
      return false
    } finally {
      setSaving(false)
    }
  }

  /** Saves one server; the other saved servers stay exactly as they were stored. */
  async function saveServer(server: McpServerEntryPayload) {
    const next = normalized(server)
    const base = saved?.servers ?? []
    const servers = base.some(s => s.id === next.id) ? base.map(s => (s.id === next.id ? next : s)) : [...base, next]
    const ok = await persist(servers, `${next.name || 'Server'} saved. Enabled servers appear in the Ask Data @ picker.`)
    if (ok) stopEditing(server.id)
  }

  function cancelEdit(server: McpServerEntryPayload) {
    const stored = saved?.servers.find(s => s.id === server.id)
    setDraft(d => ({
      ...d,
      servers: stored ? d.servers.map(s => (s.id === server.id ? stored : s)) : d.servers.filter(s => s.id !== server.id),
    }))
    stopEditing(server.id)
  }

  async function removeServer(server: McpServerEntryPayload) {
    if (!savedIds.has(server.id)) {
      setDraft(d => ({ ...d, servers: d.servers.filter(s => s.id !== server.id) }))
      return
    }
    if (!window.confirm(`Remove "${server.name || 'this server'}"? It will disappear from the @ picker.`)) return
    await persist(
      (saved?.servers ?? []).filter(s => s.id !== server.id),
      `${server.name || 'Server'} removed.`,
    )
  }

  async function toggleEnabled(server: McpServerEntryPayload, enabled: boolean) {
    await persist(
      (saved?.servers ?? []).map(s => (s.id === server.id ? { ...s, enabled } : s)),
      `${server.name} ${enabled ? 'enabled' : 'disabled'}.`,
    )
  }

  async function testServer(server: McpServerEntryPayload) {
    setTestingId(server.id)
    setResults(r => {
      const copy = { ...r }
      delete copy[server.id]
      return copy
    })
    try {
      const result: McpTestConnectionResult = await api.testMcpConnection(normalized(server))
      const ms = result.latency_ms > 0 ? ` (${result.latency_ms} ms)` : ''
      setResults(r => ({ ...r, [server.id]: { ok: result.ok, message: `${result.message}${ms}` } }))
    } catch (e) {
      setResults(r => ({ ...r, [server.id]: { ok: false, message: safeErrorMessage(toAppApiError(e)) } }))
    } finally {
      setTestingId(null)
    }
  }

  function updateServer(id: string, patch: Partial<McpServerEntryPayload>) {
    setDraft(d => ({ ...d, servers: d.servers.map(s => (s.id === id ? { ...s, ...patch } : s)) }))
  }

  function addServer(server: McpServerEntryPayload) {
    setDraft(d => ({ ...d, servers: [...d.servers, server] }))
  }

  if (loading) {
    return <p className="type-chat-body text-slate-500">Loading MCP settings…</p>
  }

  return (
    <div className={`space-y-4 ${embedded ? '' : 'border-t border-slate-100 pt-6'}`}>
      <div>
        <h2 className="text-[15px] font-semibold text-cloudera-navy">
          {embedded ? 'Connections' : 'MCP connections'}
        </h2>
        <p className="type-chat-meta mt-1 text-slate-500">
          Standard MCP (stdio or SSE). Secrets stay in backend environment — reference env var names only.
          Use @ in Ask Data to attach a server for that message.
        </p>
      </div>
      {error ? <p className="text-xs text-rose-700">{safeErrorMessage(error)}</p> : null}
      {banner ? <p className="text-xs text-emerald-800">{banner}</p> : null}

      {draft.servers.map(server => {
        const editing = isEditing(server)
        const result = results[server.id]
        const testButton = (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-xl border-2 border-cloudera-violet bg-white px-3.5 py-1.5 text-xs font-semibold text-cloudera-violet transition hover:bg-violet-100 disabled:opacity-50"
            disabled={testingId === server.id || !canTest(server)}
            onClick={() => void testServer(server)}
          >
            <Plug className="h-3.5 w-3.5" aria-hidden />
            {testingId === server.id ? 'Testing…' : 'Test connection'}
          </button>
        )
        const resultLine = result ? (
          <p className={`text-xs ${result.ok ? 'text-emerald-800' : 'text-rose-700'}`} data-testid="mcp-test-result">
            {result.message}
          </p>
        ) : null

        if (!editing) {
          const target =
            server.transport === 'stdio'
              ? [server.command, ...server.args].filter(Boolean).join(' ')
              : (server.url ?? '')
          return (
            <div
              key={server.id}
              className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              data-testid="mcp-server-card"
            >
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-cloudera-navy">{server.name}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-600">
                      {server.transport}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        server.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {server.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  {server.description ? <p className="mt-1 text-xs text-slate-500">{server.description}</p> : null}
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={server.enabled}
                    disabled={saving}
                    aria-label={`Enable ${server.name}`}
                    onChange={e => void toggleEnabled(server, e.target.checked)}
                  />
                  Enabled
                </label>
              </div>
              <p className="break-all rounded-lg bg-slate-50 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-600">
                {target || '—'}
              </p>
              {server.default_tool ? (
                <p className="text-xs text-slate-500">Default tool: {server.default_tool}</p>
              ) : null}
              {resultLine}
              <div className="flex flex-wrap items-center gap-2">
                {testButton}
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
                  onClick={() => setEditingIds(ids => new Set(ids).add(server.id))}
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden />
                  Edit
                </button>
                <button
                  type="button"
                  className="ml-auto text-slate-400 hover:text-rose-600"
                  aria-label={`Remove ${server.name}`}
                  onClick={() => void removeServer(server)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          )
        }

        return (
          <div
            key={server.id}
            className="space-y-2 rounded-xl border border-slate-200/90 bg-slate-50/40 p-4"
            data-testid="mcp-server-form"
          >
            <div className="flex items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={server.enabled}
                  onChange={e => updateServer(server.id, { enabled: e.target.checked })}
                />
                Enabled
              </label>
              {!savedIds.has(server.id) ? (
                <button
                  type="button"
                  className="text-slate-500 hover:text-rose-600"
                  aria-label="Discard new server"
                  onClick={() => void removeServer(server)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              ) : null}
            </div>
            <input
              className="input"
              placeholder="Display name"
              value={server.name}
              onChange={e => updateServer(server.id, { name: e.target.value })}
            />
            <select
              className="input"
              value={server.transport}
              onChange={e => updateServer(server.id, { transport: e.target.value as 'stdio' | 'sse' })}
            >
              <option value="stdio">stdio (local command)</option>
              <option value="sse">SSE (remote URL)</option>
            </select>
            {server.transport === 'stdio' ? (
              <>
                <input
                  className="input font-mono text-xs"
                  placeholder="Command (e.g. npx)"
                  value={server.command ?? ''}
                  onChange={e => updateServer(server.id, { command: e.target.value })}
                />
                <input
                  className="input font-mono text-xs"
                  placeholder="Args (comma-separated)"
                  value={server.args.join(', ')}
                  onChange={e =>
                    updateServer(server.id, {
                      args: e.target.value
                        .split(',')
                        .map(x => x.trim())
                        .filter(Boolean),
                    })
                  }
                />
                <input
                  className="input font-mono text-xs"
                  placeholder="Env var names (comma-separated, e.g. BRAVE_API_KEY)"
                  value={server.env_var_names.join(', ')}
                  onChange={e =>
                    updateServer(server.id, {
                      env_var_names: e.target.value
                        .split(',')
                        .map(x => x.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </>
            ) : (
              <input
                className="input font-mono text-xs"
                placeholder="SSE URL"
                value={server.url ?? ''}
                onChange={e => updateServer(server.id, { url: e.target.value })}
              />
            )}
            <input
              className="input text-xs"
              placeholder="Default tool (optional)"
              value={server.default_tool ?? ''}
              onChange={e => updateServer(server.id, { default_tool: e.target.value || null })}
            />
            {resultLine}
            <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
              {savedIds.has(server.id) ? (
                <button
                  type="button"
                  className="rounded-xl border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
                  onClick={() => cancelEdit(server)}
                >
                  Cancel
                </button>
              ) : null}
              {testButton}
              <button
                type="button"
                className="btn-primary py-2 text-xs"
                disabled={saving || !server.name.trim() || !canTest(server)}
                onClick={() => void saveServer(server)}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )
      })}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-secondary py-2 text-xs" onClick={() => addServer(emptyServer())}>
          <Plus className="mr-1 inline h-3 w-3" />
          Add server
        </button>
        <button
          type="button"
          className="btn-secondary py-2 text-xs"
          onClick={() => addServer({ ...BRAVE_PRESET, id: crypto.randomUUID() })}
        >
          Add Brave Search preset
        </button>
      </div>
    </div>
  )
}
