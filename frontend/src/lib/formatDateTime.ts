const WIB = 'Asia/Jakarta'

/** Display backend UTC ISO timestamps in WIB (UTC+7). */
export function formatUsageTimestampWib(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso.replace('T', ' ').slice(0, 19)
  }
  return date.toLocaleString('sv-SE', { timeZone: WIB, hour12: false })
}
