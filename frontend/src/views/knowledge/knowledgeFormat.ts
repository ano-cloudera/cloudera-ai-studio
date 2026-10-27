import type { DocumentStatus, LibraryLifecycleStatus } from '../../types/api'

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const diffMs = Date.now() - then
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 48) return `${hours} hr ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function formatShortDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function documentStatusLabel(status: DocumentStatus): string {
  if (status === 'READY') return 'Ready'
  if (status === 'QUEUED' || status === 'PROCESSING') return 'Processing'
  if (status === 'FAILED') return 'Failed'
  return 'Uploaded'
}

export function libraryStatusLabel(status: LibraryLifecycleStatus | string | undefined): string {
  const s = (status || 'ready').toLowerCase()
  if (s === 'attention') return 'Attention'
  if (s === 'processing') return 'Processing'
  return 'Ready'
}

export function mimeShort(mime: string): string {
  if (mime.includes('pdf')) return 'PDF'
  if (mime.includes('word') || mime.includes('docx')) return 'DOCX'
  if (mime.includes('text')) return 'TXT'
  if (mime.includes('sheet') || mime.includes('excel')) return 'XLSX'
  return mime.split('/').pop()?.toUpperCase() || mime
}
