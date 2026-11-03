'use client'

import { useEffect, useState } from 'react'

type Component = { status?: string; provider?: string; model?: string; dimension?: number }
type Pipeline = { embeddings: Component | null; reranker: Component | null }

/** The last part of a model path or id ("/home/cdsw/models/bge-m3" -> "bge-m3"). */
export function shortModelName(model: string | undefined): string {
  if (!model) return ''
  return model.replace(/\/+$/, '').split('/').pop() ?? model
}

export function describeEmbedding(component: Component | null): string {
  if (!component) return 'Not reported'
  const parts = [component.provider, shortModelName(component.model), component.dimension ? `${component.dimension} dimensions` : '']
  return parts.filter(Boolean).join(' · ') || 'Not reported'
}

export function describeReranker(component: Component | null): string {
  if (!component) return 'Not reported'
  if (!component.provider || component.provider === 'none') return 'Not used: results are ordered by vector score'
  return [component.provider, shortModelName(component.model)].filter(Boolean).join(' · ')
}

function StatusBadge({ status }: { status?: string }) {
  const ready = status === 'ready'
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${ready ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'}`}>
      {ready ? 'Ready' : status ? status.replace(/_/g, ' ') : 'Unknown'}
    </span>
  )
}

/** Read-only: how documents are indexed and searched is decided by the Backend environment, not by the model registry. */
export function RetrievalPipelineCard() {
  const [pipeline, setPipeline] = useState<Pipeline | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    fetch('/api/health/ready')
      .then(async response => {
        // A 503 still carries the component report, so read the body whatever the status.
        const body = (await response.json()) as { components?: { embeddings?: Component; reranker?: Component } }
        if (alive) setPipeline({ embeddings: body.components?.embeddings ?? null, reranker: body.components?.reranker ?? null })
      })
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
    }
  }, [])

  return (
    <section className="space-y-3" aria-labelledby="retrieval-pipeline-title">
      <div>
        <h3 id="retrieval-pipeline-title" className="text-sm font-semibold text-cloudera-navy">
          Retrieval pipeline
        </h3>
        <p className="type-chat-meta mt-1 max-w-2xl text-slate-500">
          How Knowledge documents are indexed and searched. This is set by the Backend environment, so it is shown here but not edited here.
        </p>
      </div>
      {failed ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">
          The Backend did not report its retrieval settings.
        </p>
      ) : (
        <dl className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm">
            <dt className="flex items-center gap-2 text-sm font-semibold text-cloudera-navy">
              Embedding model {pipeline ? <StatusBadge status={pipeline.embeddings?.status} /> : null}
            </dt>
            <dd className="mt-1 text-sm text-slate-700">{pipeline ? describeEmbedding(pipeline.embeddings) : 'Loading…'}</dd>
            <dd className="type-chat-meta mt-1 text-slate-500">Turns text into vectors. Changing it means indexing every library again.</dd>
          </div>
          <div className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm">
            <dt className="flex items-center gap-2 text-sm font-semibold text-cloudera-navy">
              Reranker {pipeline ? <StatusBadge status={pipeline.reranker?.status} /> : null}
            </dt>
            <dd className="mt-1 text-sm text-slate-700">{pipeline ? describeReranker(pipeline.reranker) : 'Loading…'}</dd>
            <dd className="type-chat-meta mt-1 text-slate-500">Re-scores the best passages so the most relevant ones reach the answer.</dd>
          </div>
        </dl>
      )}
      <p className="type-chat-meta max-w-2xl text-slate-500">
        To use a reranker, add the project variable <code>ENABLE_RERANKER</code> = <code>true</code>, then run the install and deploy Jobs (see the README).
      </p>
    </section>
  )
}
