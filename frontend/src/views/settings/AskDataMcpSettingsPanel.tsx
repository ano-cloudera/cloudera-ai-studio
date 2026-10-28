'use client'

import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
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

type Props = {
  embedded?: boolean
}

export function AskDataMcpSettingsPanel({ embedded = false }: Props) {
  const [draft, setDraft] = useState<McpWorkspaceSettingsPayload>({ servers: [] })
  const [saved, setSaved] = useState<McpWorkspaceSettingsPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<AppApiError | null>(null)
  const [banner, setBanner] = useState('')
  const [testing, setTesting] = useState(false)
  const [testFeedback, setTestFeedback] = useState<{ ok: boolean; message: string } | null>(null)

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

  const dirty = saved != null && JSON.stringify(draft) !== JSON.stringify(saved)

  async function save() {
    setSaving(true)
    setBanner('')
    setError(null)
    try {
      const servers = draft.servers
        .map(s => ({
          ...s,
          name: s.name.trim(),
          command: s.transport === 'stdio' ? (s.command || '').trim() || null : null,
          url: s.transport === 'sse' ? (s.url || '').trim() || null : null,
        }))
        .filter(s => s.name)
      const response = await api.putMcpSettings({ servers })
      setDraft(response.settings)
      setSaved(response.settings)
      setBanner('MCP connections saved. Enabled servers appear in Ask Data @ picker.')
    } catch (e) {
      setError(toAppApiError(e))
    } finally {
      setSaving(false)
    }
  }

  function updateServer(index: number, patch: Partial<McpServerEntryPayload>) {
    setDraft(d => {
      const servers = [...d.servers]
      servers[index] = { ...servers[index], ...patch }
      return { ...d, servers }
    })
  }

  function removeServer(index: number) {
    setDraft(d => ({ ...d, servers: d.servers.filter((_, i) => i !== index) }))
  }

  function serverPayloadForTest(server: McpServerEntryPayload): McpServerEntryPayload {
    return {
      ...server,
      name: server.name.trim(),
      command: server.transport === 'stdio' ? (server.command || '').trim() || null : null,
      url: server.transport === 'sse' ? (server.url || '').trim() || null : null,
    }
  }

  function canTestServer(server: McpServerEntryPayload): boolean {
    if (!server.name.trim()) return false
    if (server.transport === 'stdio') return !!(server.command || '').trim()
    return !!(server.url || '').trim()
  }

  const testableServerCount = draft.servers.filter(canTestServer).length

  async function testConnections() {
    const targets = draft.servers
      .map((server, index) => ({ server, index }))
      .filter(({ server }) => canTestServer(server))
    if (!targets.length) {
      setTestFeedback({
        ok: false,
        message: 'Add at least one server with display name and command or SSE URL.',
      })
      return
    }

    setTesting(true)
    setTestFeedback(null)
    setBanner('')
    const lines: string[] = []
    let allOk = true
    try {
      for (const { server } of targets) {
        const label = server.name.trim() || 'Server'
        try {
          const result: McpTestConnectionResult = await api.testMcpConnection(serverPayloadForTest(server))
          if (!result.ok) allOk = false
          const ms = result.latency_ms > 0 ? ` (${result.latency_ms} ms)` : ''
          lines.push(`${label}: ${result.message}${ms}`)
        } catch (e) {
          allOk = false
          lines.push(`${label}: ${safeErrorMessage(toAppApiError(e))}`)
        }
      }
      setTestFeedback({ ok: allOk, message: lines.join(' · ') })
    } finally {
      setTesting(false)
    }
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
      {testFeedback ? (
        <p className={`text-xs ${testFeedback.ok ? 'text-emerald-800' : 'text-rose-700'}`}>{testFeedback.message}</p>
      ) : null}

      {draft.servers.map((server, index) => (
        <div key={server.id || index} className="space-y-2 rounded-xl border border-slate-200/90 bg-slate-50/40 p-4">
          <div className="flex items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={server.enabled}
                onChange={e => updateServer(index, { enabled: e.target.checked })}
              />
              Enabled
            </label>
            <button type="button" className="text-slate-500 hover:text-rose-600" onClick={() => removeServer(index)}>
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
          <input
            className="input"
            placeholder="Display name"
            value={server.name}
            onChange={e => updateServer(index, { name: e.target.value })}
          />
          <select
            className="input"
            value={server.transport}
            onChange={e => updateServer(index, { transport: e.target.value as 'stdio' | 'sse' })}
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
                onChange={e => updateServer(index, { command: e.target.value })}
              />
              <input
                className="input font-mono text-xs"
                placeholder="Args (comma-separated)"
                value={server.args.join(', ')}
                onChange={e =>
                  updateServer(index, {
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
                  updateServer(index, {
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
              onChange={e => updateServer(index, { url: e.target.value })}
            />
          )}
          <input
            className="input text-xs"
            placeholder="Default tool (optional)"
            value={server.default_tool ?? ''}
            onChange={e => updateServer(index, { default_tool: e.target.value || null })}
          />
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-secondary py-2 text-xs" onClick={() => setDraft(d => ({ ...d, servers: [...d.servers, emptyServer()] }))}>
          <Plus className="mr-1 inline h-3 w-3" />
          Add server
        </button>
        <button
          type="button"
          className="btn-secondary py-2 text-xs"
          onClick={() =>
            setDraft(d => ({
              ...d,
              servers: [...d.servers, { ...BRAVE_PRESET, id: crypto.randomUUID() }],
            }))
          }
        >
          Add Brave Search preset
        </button>
        <div className="ml-auto flex flex-wrap gap-2">
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-xl border-2 border-cloudera-violet bg-white px-4 py-2 text-xs font-semibold text-cloudera-violet transition hover:bg-violet-100 disabled:opacity-50"
            disabled={testing || testableServerCount === 0}
            onClick={() => void testConnections()}
          >
            {testing ? 'Testing…' : 'Test connection'}
          </button>
          <button type="button" className="btn-primary py-2 text-xs" disabled={!dirty || saving} onClick={() => void save()}>
            {saving ? 'Saving…' : 'Save MCP connections'}
          </button>
        </div>
      </div>
    </div>
  )
}
