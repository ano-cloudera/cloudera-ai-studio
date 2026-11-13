'use client'

/*
 * Actions: the record of actions a person approved with Run, kept by the platform whatever MCP server they were sent to.
 * It shows what was asked (the arguments as sent) and what came back, so it holds for any action, not one kind of record.
 * It is a log people can tidy, so a record can be deleted (one or several); the action itself is not undone by that.
 */

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageCenter } from '../components/PageCenter'
import { StatusPill } from '../components/StatusPill'
import { BulkDeleteDialog } from '../components/table/BulkDeleteDialog'
import { RowActionsMenu } from '../components/table/RowActionsMenu'
import { TableSelectionActionBar } from '../components/table/TableSelectionActionBar'
import { TableHeaderCheckbox, TableRowCheckbox } from '../components/table/TableSelectionCheckbox'
import { TablePagination } from '../components/knowledge/TablePagination'
import { SimpleModal } from '../components/knowledge/SimpleModal'
import { api } from '../lib/api'
import { useTableSelection } from '../lib/useTableSelection'
import { useTableSelectionMode } from '../lib/useTableSelectionMode'
import type { ActionRecord } from '../types/api'

const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange'

function stamp(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function show(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function took(ms: number | null | undefined): string | null {
  if (typeof ms !== 'number') return null
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

/** The reply of a tool as lines a person reads: a JSON object becomes its fields, anything else stays as text. */
function replyLines(result: string): [string, string][] {
  try {
    const parsed = JSON.parse(result)
    const record = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (Object.values(parsed).length === 1 && typeof Object.values(parsed)[0] === 'object' ? Object.values(parsed)[0] : parsed) : null
    if (record && typeof record === 'object') {
      return Object.entries(record as Record<string, unknown>)
        .filter(([, value]) => value !== null && value !== '')
        .map(([key, value]) => [key.replaceAll('_', ' '), show(value)])
    }
  } catch {
    // not JSON: shown as it came
  }
  return result.trim() ? [['reply', result.trim()]] : []
}

function Details({ action }: { action: ActionRecord }) {
  const sent = Object.entries(action.arguments).filter(([, value]) => value !== null && value !== '')
  const facts: [string, string][] = [
    ['Server', action.server],
    ['Tool', action.tool],
    ['Created', stamp(action.at)],
    ...(took(action.duration_ms) ? ([['Run time', took(action.duration_ms) as string]] as [string, string][]) : []),
    ...(action.request_id ? ([['Answer', action.request_id]] as [string, string][]) : []),
    ['Record', action.id],
  ]
  return (
    <div className="space-y-4 text-sm text-slate-700">
      <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[auto_1fr]">
        {facts.map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="font-medium text-slate-600">{key}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
      <dl className="grid gap-x-3 gap-y-1 border-t border-slate-100 pt-3 sm:grid-cols-[auto_1fr]">
        <dt className="col-span-full font-semibold text-cloudera-navy">Sent</dt>
        {sent.map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="font-medium capitalize text-slate-600">{key.replaceAll('_', ' ')}</dt>
            <dd className="min-w-0 break-words">{show(value)}</dd>
          </div>
        ))}
      </dl>
      <dl className="grid gap-x-3 gap-y-1 border-t border-slate-100 pt-3 sm:grid-cols-[auto_1fr]">
        <dt className="col-span-full font-semibold text-cloudera-navy">{action.status === 'ok' ? 'Came back' : 'Error'}</dt>
        {action.status === 'ok' ? (
          replyLines(action.result).map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="font-medium capitalize text-slate-600">{key}</dt>
              <dd className="min-w-0 break-words">{value}</dd>
            </div>
          ))
        ) : (
          <dd className="col-span-full break-words">{action.error}</dd>
        )}
      </dl>
    </div>
  )
}

type State = { status: 'loading' } | { status: 'failed'; message: string } | { status: 'ok'; actions: ActionRecord[] }

export function ActionsPage() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [detail, setDetail] = useState<ActionRecord | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'ok' | 'failed'>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const selection = useTableSelection()
  const selectionMode = useTableSelectionMode(selection.clear)

  const load = useCallback(() => {
    setState({ status: 'loading' })
    api
      .mcpActionHistory()
      .then(({ actions }) => setState({ status: 'ok', actions }))
      .catch(error => setState({ status: 'failed', message: (error as { message?: string })?.message || 'The action history could not be read.' }))
  }, [])

  useEffect(load, [load])

  const all = state.status === 'ok' ? state.actions : []
  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return all.filter(
      action =>
        (statusFilter === 'all' || action.status === statusFilter) &&
        (!needle || [action.title, action.server, action.tool].some(text => text.toLowerCase().includes(needle))),
    )
  }, [all, search, statusFilter])
  const paged = useMemo(() => rows.slice((page - 1) * pageSize, page * pageSize), [rows, page, pageSize])

  useEffect(() => {
    const pages = Math.max(1, Math.ceil(rows.length / pageSize))
    if (page > pages) setPage(pages)
  }, [rows.length, page, pageSize])

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    setDeleteError('')
    try {
      await api.deleteMcpActions(pendingDelete)
      if (detail && pendingDelete.includes(detail.id)) setDetail(null)
      setPendingDelete(null)
      selectionMode.exit()
      load()
    } catch (error) {
      setDeleteError((error as { message?: string })?.message || 'The records could not be deleted.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <PageCenter>
      <div className="mb-4 max-w-3xl" data-testid="actions-page">
        <h1 className="type-app-title text-2xl">Actions</h1>
        <p className="type-chat-body mt-1 text-slate-500">
          Every action the agent proposed and a person approved with Run, with what was sent and what came back. The record is kept by this platform, whichever MCP server received the action.
        </p>
      </div>

      {state.status === 'failed' && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          <span>{state.message}</span>
          <button type="button" onClick={load} className={`min-h-11 rounded-lg border border-rose-300 bg-white px-4 font-semibold hover:bg-rose-100 ${FOCUS}`}>
            Try again
          </button>
        </div>
      )}

      {state.status === 'loading' && (
        <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Reading the action history…
        </p>
      )}

      {state.status === 'ok' && all.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-700">
          <p>
            No action has been run yet. When you ask the agent what to do about a problem, it can propose actions from the MCP servers enabled in Settings; each one runs only after you approve it with Run, and it is recorded here.
          </p>
          <Link href="/" className={`mt-2 inline-block font-semibold text-cloudera-navy underline underline-offset-2 ${FOCUS}`}>
            Open Ask Data
          </Link>
        </div>
      )}

      {state.status === 'ok' && all.length > 0 && (
        <section className="app-table-surface" data-testid="actions-table-panel">
          <div className="space-y-2 border-b border-slate-100 px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="search"
                aria-label="Search actions"
                placeholder="Search actions…"
                value={search}
                onChange={event => {
                  setSearch(event.target.value)
                  setPage(1)
                }}
                className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
              <select
                aria-label="Filter by result"
                className="app-select-filter"
                value={statusFilter}
                onChange={event => {
                  setStatusFilter(event.target.value as 'all' | 'ok' | 'failed')
                  setPage(1)
                }}
              >
                <option value="all">All results</option>
                <option value="ok">Done</option>
                <option value="failed">Failed</option>
              </select>
              <TableSelectionActionBar
                entityLabel="actions"
                mode={selectionMode}
                selectedCount={selection.selectedCount}
                showDelete
                onDelete={() => setPendingDelete(selection.selectedList)}
              />
              <button type="button" onClick={load} className="btn-secondary px-3 py-2 text-sm">
                Refresh
              </button>
            </div>
          </div>
          <div className="app-table-surface-scroll">
            <table className="app-data-table min-w-full table-fixed">
              <thead className="app-table-head">
                <tr>
                  {selectionMode.active ? (
                    <th className="w-11 px-2 py-2">
                      <TableHeaderCheckbox
                        state={selection.datasetCheckboxState(rows.length)}
                        onToggle={() =>
                          selection.toggleDatasetSelection(
                            rows.map(action => action.id),
                            rows.length,
                          )
                        }
                      />
                    </th>
                  ) : null}
                  <th className="px-3 py-2">Action</th>
                  <th className="w-40 px-3 py-2">Server</th>
                  <th className="w-36 px-3 py-2">Tool</th>
                  <th className="w-28 px-3 py-2">Result</th>
                  <th className="w-44 px-3 py-2">Created</th>
                  <th className="w-24 px-3 py-2 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={selectionMode.active ? 7 : 6} className="px-3 py-8 text-center text-slate-500">
                      No action matches this search.
                    </td>
                  </tr>
                ) : (
                  paged.map(action => (
                    <tr key={action.id}>
                      {selectionMode.active ? (
                        <td className="w-11 px-2 py-2">
                          <TableRowCheckbox checked={selection.isSelected(action.id)} label={`Select ${action.title}`} onToggle={() => selection.toggle(action.id)} />
                        </td>
                      ) : null}
                      <td className="px-3 py-2">
                        <button type="button" onClick={() => setDetail(action)} className={`text-left font-semibold text-cloudera-navy hover:underline ${FOCUS}`}>
                          {action.title}
                        </button>
                      </td>
                      <td className="truncate px-3 py-2 text-slate-700" title={action.server}>
                        {action.server}
                      </td>
                      <td className="truncate px-3 py-2 text-slate-600" title={action.tool}>
                        {action.tool}
                      </td>
                      <td className="px-3 py-2">
                        <StatusPill label={action.status === 'ok' ? 'Done' : 'Failed'} tone={action.status === 'ok' ? 'green' : 'red'} />
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-600">{stamp(action.at)}</td>
                      <td className="px-3 py-2">
                        <RowActionsMenu
                          label={`Actions for ${action.title}`}
                          items={[
                            { key: 'view', label: 'View details', onClick: () => setDetail(action) },
                            { key: 'sep', separator: true },
                            { key: 'delete', label: 'Delete', danger: true, onClick: () => setPendingDelete([action.id]) },
                          ]}
                        />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {rows.length > 0 ? (
            <TablePagination
              page={page}
              pageSize={pageSize}
              total={rows.length}
              onPageChange={setPage}
              onPageSizeChange={size => {
                setPageSize(size)
                setPage(1)
              }}
            />
          ) : null}
        </section>
      )}

      {detail ? (
        <SimpleModal title={detail.title} onClose={() => setDetail(null)}>
          <Details action={detail} />
        </SimpleModal>
      ) : null}

      {pendingDelete ? (
        <BulkDeleteDialog
          count={pendingDelete.length}
          entityLabel="action"
          description={`This removes ${pendingDelete.length === 1 ? 'the record' : 'the records'} from this log. What the action already did on its server is not undone.${deleteError ? ` ${deleteError}` : ''}`}
          loading={deleting}
          onCancel={() => {
            setPendingDelete(null)
            setDeleteError('')
          }}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}
    </PageCenter>
  )
}
