export type ChatAttachmentStatus =
  | 'UPLOADING'
  | 'QUEUED'
  | 'PROCESSING'
  | 'READY'
  | 'FAILED'
  | 'EXPIRED'

export type ChatAttachmentRecord = {
  id: string
  session_id: string
  filename: string
  display_name: string
  mime_type: string
  size_bytes: number
  status: ChatAttachmentStatus
  error_message?: string | null
  chunk_count?: number | null
  page_count?: number | null
}

export function attachmentBlocksSend(
  status: ChatAttachmentStatus | undefined,
  chunkCount?: number | null,
): boolean {
  if (!status) return false
  if (status === 'FAILED' || status === 'EXPIRED') return true
  if (status !== 'READY') return true
  if (chunkCount != null && chunkCount <= 0) return true
  return false
}

export function attachmentContextBlocksSend(
  sources: { type: string; metadata?: Record<string, unknown> }[],
): boolean {
  return sources.some(source => {
    if (source.type !== 'uploaded_file') return false
    const status = source.metadata?.status as ChatAttachmentStatus | undefined
    const chunkCount = source.metadata?.chunk_count as number | undefined
    return attachmentBlocksSend(status, chunkCount)
  })
}

export function attachmentStatusLabel(status: ChatAttachmentStatus | undefined): string {
  switch (status) {
    case 'UPLOADING':
      return 'Uploading…'
    case 'QUEUED':
      return 'Queued'
    case 'PROCESSING':
      return 'Processing document…'
    case 'READY':
      return 'Ready'
    case 'FAILED':
      return 'Processing failed'
    case 'EXPIRED':
      return 'Expired'
    default:
      return 'Processing…'
  }
}
