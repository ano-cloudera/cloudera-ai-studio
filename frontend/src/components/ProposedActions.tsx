'use client'

import Link from 'next/link'
import { useState } from 'react'
import { CheckCircle2, Loader2, Play, ShieldCheck, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import type { ProposedAction } from '../types/api'

const TEXT = {
  id: { heading: 'Aksi yang diusulkan', note: 'Tidak ada yang dijalankan sampai Anda menyetujuinya.', run: 'Jalankan', running: 'Menjalankan…', done: 'Selesai', failed: 'Gagal', retry: 'Coba lagi', seeTickets: 'Lihat semua tiket' },
  en: { heading: 'Proposed actions', note: 'Nothing runs until you approve it.', run: 'Run', running: 'Running…', done: 'Done', failed: 'Failed', retry: 'Retry', seeTickets: 'See all tickets' },
} as const

type State = { status: 'idle' | 'running' | 'done' | 'failed'; message?: string }

/** A short line from the tool's reply: a created record's id and title, else the first line. */
function summarise(result: string): string {
  try {
    const parsed = JSON.parse(result)
    const record = parsed?.created ?? parsed
    if (record && typeof record === 'object' && (record.id || record.title)) {
      return [record.id, record.title, record.due_date ? `→ ${record.due_date}` : ''].filter(Boolean).join(' · ')
    }
    if (parsed?.error) return String(parsed.error)
  } catch {
    // not JSON: shown as text
  }
  return result.split('\n').find(line => line.trim())?.slice(0, 200) ?? ''
}

function argumentLines(action: ProposedAction): [string, string][] {
  return Object.entries(action.arguments)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => [key.replaceAll('_', ' '), typeof value === 'string' ? value : JSON.stringify(value)])
}

export function ProposedActions({ actions, language }: { actions: ProposedAction[]; language?: string | null }) {
  const text = TEXT[language === 'id' ? 'id' : 'en']
  const [states, setStates] = useState<Record<string, State>>({})
  if (!actions.length) return null

  const run = async (action: ProposedAction) => {
    setStates(current => ({ ...current, [action.id]: { status: 'running' } }))
    try {
      const reply = await api.runMcpAction({ server_id: action.server_id, tool: action.tool, arguments: action.arguments })
      setStates(current => ({ ...current, [action.id]: { status: 'done', message: summarise(reply.result) } }))
    } catch (error) {
      const message = (error as { message?: string })?.message || ''
      setStates(current => ({ ...current, [action.id]: { status: 'failed', message } }))
    }
  }

  return (
    <div className="answer-section-divider space-y-2 !pt-3" data-testid="proposed-actions">
      <div className="flex flex-wrap items-center gap-2">
        <span className="type-section-label">{text.heading}</span>
        <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
          <ShieldCheck size={12} aria-hidden /> {text.note}
        </span>
      </div>
      {actions.map(action => {
        const state = states[action.id] ?? { status: 'idle' }
        return (
          <div key={action.id} className="rounded-xl border border-violet-200 bg-violet-50/50 p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-cloudera-navy">{action.title}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">
                  {action.server} · {action.tool}
                </div>
                <dl className="mt-2 grid gap-x-3 gap-y-0.5 text-xs text-slate-700 sm:grid-cols-[auto_1fr]">
                  {argumentLines(action).map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="font-medium capitalize text-slate-500">{key}</dt>
                      <dd className="min-w-0 break-words">{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              {state.status === 'done' ? (
                <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
                  <CheckCircle2 size={14} aria-hidden /> {text.done}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => run(action)}
                  disabled={state.status === 'running'}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-cloudera-navy px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                >
                  {state.status === 'running' ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <Play size={14} aria-hidden />}
                  {state.status === 'running' ? text.running : state.status === 'failed' ? text.retry : text.run}
                </button>
              )}
            </div>
            {state.status === 'done' && (
              <p className="mt-2 text-xs text-emerald-800" role="status">
                {state.message}{' '}
                <Link href="/tickets" className="font-semibold underline underline-offset-2">
                  {text.seeTickets}
                </Link>
              </p>
            )}
            {state.status === 'failed' && (
              <p className="mt-2 inline-flex items-center gap-1 text-xs text-rose-700" role="alert">
                <XCircle size={12} aria-hidden /> {text.failed}
                {state.message ? `: ${state.message}` : ''}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
