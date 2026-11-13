'use client'

/*
 * Tickets: the follow-up tickets raised through actions the agent proposed and a person approved. They live in the MCP server
 * that holds them (its read-only tool list_tickets), so this page only reads; nothing here creates or changes a ticket.
 */

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { pageCenterClassName } from '../components/PageCenter'
import { api } from '../lib/api'

type Ticket = {
  id: string
  title: string
  description?: string
  priority?: string
  location?: string | null
  assignee_role?: string | null
  due_date?: string | null
  evidence?: string | null
  status?: string
  created_at?: string
}

const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange'
const PRIORITY_ORDER = ['critical', 'high', 'medium', 'low']
const PRIORITY_STYLE: Record<string, string> = {
  critical: 'bg-rose-100 text-rose-900',
  high: 'bg-orange-100 text-orange-900',
  medium: 'bg-slate-100 text-slate-800',
  low: 'bg-slate-50 text-slate-700',
}

function when(iso?: string | null): string {
  if (!iso) return 'Not set'
  const date = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: 'numeric' }).format(date)
}

type State = { status: 'loading' } | { status: 'no_server' } | { status: 'failed'; message: string } | { status: 'ok'; tickets: Ticket[]; server: string }

export function TicketsPage() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [open, setOpen] = useState<string | null>(null)

  const load = useCallback(() => {
    setState({ status: 'loading' })
    api
      .readableMcpTools()
      .then(async ({ tools }) => {
        const source = tools.find(tool => tool.tool === 'list_tickets')
        if (!source) {
          setState({ status: 'no_server' })
          return
        }
        const reply = await api.readMcpTool({ server_id: source.server_id, tool: 'list_tickets', arguments: { status: 'all', limit: 100 } })
        const parsed = JSON.parse(reply.result) as { tickets?: Ticket[] }
        setState({ status: 'ok', tickets: parsed.tickets ?? [], server: source.server })
      })
      .catch(error => setState({ status: 'failed', message: (error as { message?: string })?.message || 'The tickets could not be read.' }))
  }, [])

  useEffect(load, [load])

  const tickets =
    state.status === 'ok'
      ? [...state.tickets].sort((a, b) => PRIORITY_ORDER.indexOf(a.priority ?? 'low') - PRIORITY_ORDER.indexOf(b.priority ?? 'low') || String(b.created_at).localeCompare(String(a.created_at)))
      : []

  return (
    <div className={pageCenterClassName('space-y-5')} data-testid="tickets-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-cloudera-navy">Tickets</h1>
          <p className="mt-1 text-sm text-slate-600">
            Follow-up tickets raised from the agent&apos;s proposed actions, after a person approved them.
            {state.status === 'ok' && <span> Held by {state.server}.</span>}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={state.status === 'loading'}
          className={`min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 hover:border-slate-400 active:bg-slate-50 disabled:opacity-60 ${FOCUS}`}
        >
          {state.status === 'loading' ? 'Loading…' : 'Refresh'}
        </button>
      </header>

      {state.status === 'loading' && (
        <p role="status" className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Reading tickets from the MCP server…
        </p>
      )}
      {state.status === 'no_server' && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-700">
          <p>No MCP server with a ticket list is enabled. Add the Operations Desk server, then ask the agent what to do about a problem and approve its proposed ticket.</p>
          <Link href="/settings" className={`mt-2 inline-block font-semibold text-cloudera-navy underline underline-offset-2 ${FOCUS}`}>
            Open Settings, MCP
          </Link>
        </div>
      )}
      {state.status === 'failed' && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          <span>{state.message}</span>
          <button type="button" onClick={load} className={`min-h-11 rounded-lg border border-rose-300 bg-white px-4 font-semibold hover:bg-rose-100 ${FOCUS}`}>
            Try again
          </button>
        </div>
      )}
      {state.status === 'ok' && tickets.length === 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-700">
          <p>No tickets yet. Ask the agent what to do about a problem in your data; when it proposes a ticket, approve it with Run and it appears here.</p>
          <Link href="/" className={`mt-2 inline-block font-semibold text-cloudera-navy underline underline-offset-2 ${FOCUS}`}>
            Open Ask Data
          </Link>
        </div>
      )}
      {state.status === 'ok' && tickets.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <caption className="sr-only">Follow-up tickets, highest priority first</caption>
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-700">
              <tr>
                {['Ticket', 'Priority', 'Location', 'Owner', 'Due', 'Status'].map(heading => (
                  <th key={heading} scope="col" className="px-4 py-3 font-semibold">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-800">
              {tickets.map(ticket => {
                const expanded = open === ticket.id
                return (
                  <tr key={ticket.id} className="align-top">
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        onClick={() => setOpen(expanded ? null : ticket.id)}
                        className={`text-left font-semibold text-cloudera-navy hover:underline ${FOCUS}`}
                      >
                        {ticket.title}
                      </button>
                      <div className="mt-0.5 text-xs text-slate-600">
                        {ticket.id} · created {when(ticket.created_at)}
                      </div>
                      {expanded && (
                        <dl className="mt-3 space-y-2 text-xs text-slate-700">
                          {ticket.description && (
                            <div>
                              <dt className="font-semibold text-slate-600">What to do</dt>
                              <dd className="max-w-xl">{ticket.description}</dd>
                            </div>
                          )}
                          {ticket.evidence && (
                            <div>
                              <dt className="font-semibold text-slate-600">Evidence from the data</dt>
                              <dd className="max-w-xl">{ticket.evidence}</dd>
                            </div>
                          )}
                        </dl>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-md px-2 py-0.5 text-xs font-semibold capitalize ${PRIORITY_STYLE[ticket.priority ?? 'low'] ?? PRIORITY_STYLE.low}`}>{ticket.priority ?? 'low'}</span>
                    </td>
                    <td className="px-4 py-3">{ticket.location || 'Not set'}</td>
                    <td className="px-4 py-3">{ticket.assignee_role || 'Not set'}</td>
                    <td className="whitespace-nowrap px-4 py-3">{when(ticket.due_date)}</td>
                    <td className="px-4 py-3 capitalize">{ticket.status ?? 'open'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
