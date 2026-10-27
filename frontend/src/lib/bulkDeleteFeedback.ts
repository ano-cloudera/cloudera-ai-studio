import type { BulkDeleteResponse } from '../types/api'

export function bulkDeleteSummary(result: BulkDeleteResponse, entityLabel: string): string {
  const plural = result.deleted_count === 1 ? entityLabel : `${entityLabel}s`
  if (result.failed_count === 0) {
    return `${result.deleted_count} ${plural} deleted`
  }
  return `${result.deleted_count} ${plural} deleted. ${result.failed_count} failed.`
}

export function bulkDeleteFailureDetails(result: BulkDeleteResponse): string {
  if (!result.failed.length) return ''
  return result.failed.map(item => `${item.name} — ${item.message}`).join('\n')
}
