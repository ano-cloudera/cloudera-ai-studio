'use client'

import { Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { safeErrorMessage } from '../../lib/apiError'
import { useModelSelection } from '../../lib/modelSelection'
import type { SemanticBenchmarkResult, SemanticBenchmarkRun, SemanticExample } from '../../types/api'

const MAX_INSTRUCTIONS = 4000

const STATUS_TONE: Record<string, string> = {
  pass: 'bg-emerald-50 text-emerald-800',
  fail: 'bg-red-50 text-red-800',
  error: 'bg-amber-50 text-amber-800',
  answered: 'bg-slate-100 text-slate-600',
}

/** One example per line: `question | expected value | tolerance | row text` (everything after the question is optional). */
export function parseExampleLines(text: string): SemanticExample[] {
  return text
    .split('\n')
    .map(line => line.trim())
    .filter(line => line && !line.startsWith('#'))
    .map(line => {
      const [question, expected, tolerance, match] = line.split('|').map(part => part.trim())
      const value = expected === undefined || expected === '' ? null : Number(expected.replace(',', '.'))
      const allowed = tolerance === undefined || tolerance === '' ? 0.05 : Number(tolerance.replace(',', '.'))
      return {
        question,
        expected_value: value !== null && Number.isFinite(value) ? value : null,
        tolerance: Number.isFinite(allowed) && allowed >= 0 ? allowed : 0.05,
        match: match || null,
      }
    })
    .filter(example => example.question)
}

function blankExample(): SemanticExample {
  return { question: '', expected_value: null, tolerance: 0.05, match: null }
}

/** What this model should know beyond its definitions, and a check that it still answers correctly. */
export function SemanticQualityTabPanel({ modelId, published }: { modelId: string; published: boolean }) {
  const { selection } = useModelSelection()
  const [instructions, setInstructions] = useState('')
  const [examples, setExamples] = useState<SemanticExample[]>([])
  const [runs, setRuns] = useState<SemanticBenchmarkRun[]>([])
  const [results, setResults] = useState<SemanticBenchmarkResult[]>([])
  const [loading, setLoading] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pasting, setPasting] = useState(false)
  const [pasted, setPasted] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const knowledge = await api.getSemanticKnowledge(modelId)
      setInstructions(knowledge.instructions)
      setExamples(knowledge.examples)
      setRuns(knowledge.runs)
      setDirty(false)
    } catch (err) {
      setError(safeErrorMessage(err, 'Unable to load answer settings'))
    } finally {
      setLoading(false)
    }
  }, [modelId])

  useEffect(() => {
    void load()
  }, [load])

  const checkedCount = examples.filter(e => e.question.trim() && e.expected_value !== null).length

  function updateExample(index: number, patch: Partial<SemanticExample>) {
    setExamples(rows => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
    setDirty(true)
  }

  async function save(): Promise<boolean> {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const cleaned = examples.filter(e => e.question.trim()).map(e => ({ ...e, question: e.question.trim(), match: e.match?.trim() || null }))
      const saved = await api.putSemanticKnowledge(modelId, { instructions, examples: cleaned })
      setExamples(saved.examples)
      setRuns(saved.runs)
      setDirty(false)
      setNotice('Saved. Instructions apply to the next answer.')
      return true
    } catch (err) {
      setError(safeErrorMessage(err, 'Save failed'))
      return false
    } finally {
      setSaving(false)
    }
  }

  async function runBenchmark() {
    if (!selection) {
      setError('No AI model is available to run the benchmark.')
      return
    }
    if (dirty && !(await save())) return
    setRunning(true)
    setError('')
    setNotice('')
    try {
      const outcome = await api.runSemanticBenchmarks(modelId, { provider: selection.provider, model: selection.model })
      setResults(outcome.results)
      setRuns(outcome.runs)
    } catch (err) {
      setError(safeErrorMessage(err, 'Benchmark failed'))
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <p className="text-sm text-slate-600">Loading…</p>

  return (
    <div className="space-y-8">
      {error ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div> : null}
      {notice ? <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800" role="status">{notice}</div> : null}

      <section className="space-y-2">
        <h3 className="text-base font-semibold text-cloudera-navy">Instructions</h3>
        <p className="text-sm text-slate-600">
          Business rules, terms and defaults that Ask Data should follow when it answers from this model, for example “Late means delivered after
          the service level” or “Report money in IDR millions”. They apply as soon as they are saved.
        </p>
        <textarea
          className="min-h-[120px] w-full rounded-lg border border-slate-200 p-3 text-sm"
          value={instructions}
          maxLength={MAX_INSTRUCTIONS}
          aria-label="Instructions"
          onChange={e => {
            setInstructions(e.target.value)
            setDirty(true)
          }}
        />
        <p className="text-xs text-slate-500">{instructions.length} / {MAX_INSTRUCTIONS}</p>
      </section>

      <section className="space-y-2">
        <h3 className="text-base font-semibold text-cloudera-navy">Example questions</h3>
        <p className="text-sm text-slate-600">
          Questions this model should answer. Add the number you expect and the benchmark below checks it. “Look at the row with” picks a row
          by text, for example a region name; leave it empty to check the first row.
        </p>
        <div className="mt-2 rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="app-table-surface-scroll">
            <table className="app-data-table min-w-[760px]">
              <thead className="app-table-head">
                <tr>
                  <th>Question</th>
                  <th className="w-32">Expected value</th>
                  <th className="w-24">Tolerance</th>
                  <th className="w-44">Look at the row with</th>
                  <th className="w-12" />
                </tr>
              </thead>
              <tbody>
                {!examples.length ? (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-slate-500">No examples yet.</td>
                  </tr>
                ) : (
                  examples.map((example, index) => (
                    <tr key={index} className="border-t border-slate-100">
                      <td>
                        <input className="input w-full" value={example.question} aria-label={`Question ${index + 1}`} onChange={e => updateExample(index, { question: e.target.value })} />
                      </td>
                      <td>
                        <input
                          className="input w-full"
                          type="number"
                          step="any"
                          value={example.expected_value ?? ''}
                          aria-label={`Expected value ${index + 1}`}
                          onChange={e => updateExample(index, { expected_value: e.target.value === '' ? null : Number(e.target.value) })}
                        />
                      </td>
                      <td>
                        <input
                          className="input w-full"
                          type="number"
                          step="any"
                          min={0}
                          value={example.tolerance}
                          aria-label={`Tolerance ${index + 1}`}
                          onChange={e => updateExample(index, { tolerance: Math.max(0, Number(e.target.value) || 0) })}
                        />
                      </td>
                      <td>
                        <input className="input w-full" value={example.match ?? ''} aria-label={`Row text ${index + 1}`} onChange={e => updateExample(index, { match: e.target.value })} />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
                          aria-label={`Remove example ${index + 1}`}
                          onClick={() => {
                            setExamples(rows => rows.filter((_, i) => i !== index))
                            setDirty(true)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
            onClick={() => {
              setExamples(rows => [...rows, blankExample()])
              setDirty(true)
            }}
          >
            <Plus className="h-4 w-4" />
            Add example
          </button>
          <button
            type="button"
            className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
            onClick={() => setPasting(value => !value)}
          >
            Paste several
          </button>
          <button type="button" className="btn-primary h-9 px-4 text-sm" disabled={saving || !dirty} onClick={() => void save()}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
        {pasting ? (
          <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs text-slate-600">One per line: question | expected value | tolerance | row text. Only the question is required.</p>
            <textarea
              className="min-h-[110px] w-full rounded-lg border border-slate-200 bg-white p-2 font-mono text-xs"
              value={pasted}
              aria-label="Examples to add"
              placeholder={'Which region has the highest late delivery rate? | 23.15 | 0.05 | Kalimantan Timur'}
              onChange={e => setPasted(e.target.value)}
            />
            <button
              type="button"
              className="btn-primary h-9 px-4 text-sm"
              disabled={!parseExampleLines(pasted).length}
              onClick={() => {
                setExamples(rows => [...rows, ...parseExampleLines(pasted)].slice(0, 50))
                setPasted('')
                setPasting(false)
                setDirty(true)
              }}
            >
              Add to the list
            </button>
          </div>
        ) : null}
      </section>

      <section className="space-y-2">
        <h3 className="text-base font-semibold text-cloudera-navy">Benchmark</h3>
        <p className="text-sm text-slate-600">
          Asks every example that has an expected value against the published model and compares the figures. Run it before and after
          publishing a new version.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-primary h-9 px-4 text-sm"
            disabled={running || !published || checkedCount === 0}
            onClick={() => void runBenchmark()}
          >
            {running ? 'Running…' : `Run benchmark (${checkedCount})`}
          </button>
          {!published ? <span className="text-xs text-slate-500">Publish the model first.</span> : null}
          {published && checkedCount === 0 ? <span className="text-xs text-slate-500">Add an expected value to at least one example.</span> : null}
        </div>

        {results.length ? (
          <div className="mt-2 rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="app-table-surface-scroll">
              <table className="app-data-table min-w-[760px]">
                <thead className="app-table-head">
                  <tr>
                    <th className="w-24">Result</th>
                    <th>Question</th>
                    <th className="w-28">Expected</th>
                    <th className="w-28">Got</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((row, index) => (
                    <tr key={index} className="border-t border-slate-100">
                      <td>
                        <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${STATUS_TONE[row.status] ?? STATUS_TONE.answered}`}>
                          {row.status === 'pass' ? 'Pass' : row.status === 'fail' ? 'Fail' : row.status === 'error' ? 'Error' : 'Answered'}
                        </span>
                      </td>
                      <td>{row.question}</td>
                      <td>{row.expected ?? '—'}</td>
                      <td>{row.actual ?? '—'}</td>
                      <td className="text-slate-600">{row.message || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {runs.length ? (
          <div>
            <h4 className="mb-1 text-sm font-semibold text-slate-700">Recent runs</h4>
            <ul className="space-y-1 text-sm text-slate-600">
              {runs.map((run, index) => (
                <li key={`${run.at}-${index}`}>
                  {run.published_version != null ? `v${run.published_version}` : 'Unpublished'} · {run.passed} of {run.total} passed · {new Date(run.at).toLocaleString()}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  )
}
