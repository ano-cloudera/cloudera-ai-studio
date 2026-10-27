'use client'

export type UploadQueueStatus = 'QUEUED' | 'UPLOADING' | 'PROCESSING' | 'READY' | 'FAILED'

export type UploadQueueItem = {
  id: string
  name: string
  status: UploadQueueStatus
  error?: string
  documentId?: string
}

type Props = {
  items: UploadQueueItem[]
  onRetry?: (id: string) => void
  onRemove?: (id: string) => void
  onClearCompleted?: () => void
}

function statusLabel(status: UploadQueueStatus): string {
  switch (status) {
    case 'QUEUED':
      return 'Queued'
    case 'UPLOADING':
      return 'Uploading…'
    case 'PROCESSING':
      return 'Processing'
    case 'READY':
      return 'Ready'
    case 'FAILED':
      return 'Failed'
    default:
      return status
  }
}

export function DocumentUploadQueue({ items, onRetry, onRemove, onClearCompleted }: Props) {
  if (!items.length) return null
  const ready = items.filter(i => i.status === 'READY').length
  const processing = items.filter(i => i.status === 'UPLOADING' || i.status === 'PROCESSING' || i.status === 'QUEUED').length
  const failed = items.filter(i => i.status === 'FAILED').length

  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-white p-3 text-sm" data-testid="document-upload-queue">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-cloudera-navy" data-testid="document-upload-summary">
          {ready} / {items.length} ready · {processing} processing · {failed} failed
        </span>
        {ready > 0 && onClearCompleted ? (
          <button type="button" className="text-xs font-semibold text-cloudera-violet hover:underline" onClick={onClearCompleted}>
            Clear completed
          </button>
        ) : null}
      </div>
      <ul className="space-y-1">
        {items.map(item => (
          <li
            key={item.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1.5"
            data-testid="document-upload-item"
          >
            <span className="truncate font-medium text-slate-800">{item.name}</span>
            <span className="flex items-center gap-2 text-xs text-slate-600" data-testid="document-upload-status">
              {statusLabel(item.status)}
              {item.status === 'FAILED' && onRetry ? (
                <button type="button" className="font-semibold text-cloudera-violet" onClick={() => onRetry(item.id)}>
                  Retry
                </button>
              ) : null}
              {(item.status === 'FAILED' || item.status === 'QUEUED') && onRemove ? (
                <button type="button" className="text-slate-500 hover:text-slate-800" onClick={() => onRemove(item.id)}>
                  Remove
                </button>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
