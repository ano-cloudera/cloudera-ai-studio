'use client'

/*
 * Actions: the record of actions a person approved with Run, kept by the platform whatever MCP server they were sent to.
 * It shows what was asked (the arguments as sent) and what came back, so it holds for any action, not one kind of record.
 */

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { pageCenterClassName } from '../components/PageCenter'
import { api } from '../lib/api'
import type { ActionRecord } from '../types/api'

const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cloudera-orange'

function stamp(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function show(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value)
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

type State = { status: 'loading' } | { status: 'failed'; message: string } | { status: 'ok'; actions: ActionRecord[] }

export function ActionsPage() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [open, setOpen] = useState<string | null>(null)

  const load = useCallback(() => {
    setState({ status: 'loading' })
    api
      .mcpActionHistory()
      .then(({ actions }) => setState({ status: 'ok', actions }))
      .catch(error => setState({ status: 'failed', message: (error as { message?: string })?.message || 'The action history could not be read.' }))
  }, [])

  useEffect(load, [load])

  return (
    <div className={pageCenterClassName('space-y-5')} data-testid="actions-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-black tracking-tight text-cloudera-navy">Actions</h1>
          <p className="mt-1 text-sm text-slate-600">
            Every action the agent proposed and a person approved with Run, with what was sent and what came back. The record is kept by this platform, whichever MCP server received the action.
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
          Reading the action history…
        </p>
      )}
      {state.status === 'failed' && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          <span>{state.message}</span>
          <button type="button" onClick={load} className={`min-h-11 rounded-lg border border-rose-300 bg-white px-4 font-semibold hover:bg-rose-100 ${FOCUS}`}>
            Try again
          </button>
        </div>
      )}
      {state.status === 'ok' && state.actions.length === 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-700">
          <p>
            No action has been run yet. When you ask the agent what to do about a problem, it can propose actions from the MCP servers enabled in Settings; each one runs only after you approve it with Run, and it is recorded here.
          </p>
          <Link href="/" className={`mt-2 inline-block font-semibold text-cloudera-navy underline underline-offset-2 ${FOCUS}`}>
            Open Ask Data
          </Link>
        </div>
      )}
      {state.status === 'ok' && state.actions.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <caption className="sr-only">Approved actions, newest first</caption>
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-700">
              <tr>
                {['Action', 'Server and tool', 'When', 'Result'].map(heading => (
                  <th key={heading} scope="col" className="px-4 py-3 font-semibold">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-800">
              {state.actions.map(action => {
                const expanded = open === action.id
                const sent = Object.entries(action.arguments).filter(([, value]) => value !== null && value !== '')
                return (
                  <tr key={action.id} className="align-top">
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        onClick={() => setOpen(expanded ? null : action.id)}
                        className={`text-left font-semibold text-cloudera-navy hover:underline ${FOCUS}`}
                      >
                        {action.title}
                      </button>
                      {expanded && (
                        <div className="mt-3 space-y-3 text-xs text-slate-700">
                          <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[auto_1fr]">
                            <dt className="col-span-full font-semibold text-slate-600">Sent</dt>
                            {sent.map(([key, value]) => (
                              <div key={key} className="contents">
                                <dt className="font-medium capitalize text-slate-600">{key.replaceAll('_', ' ')}</dt>
                                <dd className="min-w-0 max-w-xl break-words">{show(value)}</dd>
                              </div>
                            ))}
                          </dl>
                          <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[auto_1fr]">
                            <dt className="col-span-full font-semibold text-slate-600">{action.status === 'ok' ? 'Came back' : 'Error'}</dt>
                            {action.status === 'ok' ? (
                              replyLines(action.result).map(([key, value]) => (
                                <div key={key} className="contents">
                                  <dt className="font-medium capitalize text-slate-600">{key}</dt>
                                  <dd className="min-w-0 max-w-xl break-words">{value}</dd>
                                </div>
                              ))
                            ) : (
                              <dd className="col-span-full max-w-xl break-words">{action.error}</dd>
                            )}
                          </dl>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div>{action.server}</div>
                      <div className="text-xs text-slate-600">{action.tool}</div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">{stamp(action.at)}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${action.status === 'ok' ? 'bg-emerald-100 text-emerald-900' : 'bg-rose-100 text-rose-900'}`}>
                        {action.status === 'ok' ? 'Done' : 'Failed'}
                      </span>
                    </td>
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
