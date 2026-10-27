/** Compact token counts (Cursor-style: 358.8K, 1.3M). */
export function formatCompactTokens(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0'
  const abs = Math.abs(value)
  if (abs >= 1_000_000) {
    const m = value / 1_000_000
    return `${m >= 10 ? m.toFixed(0) : m.toFixed(1)}M`
  }
  if (abs >= 1_000) {
    const k = value / 1_000
    return `${k >= 100 ? k.toFixed(0) : k.toFixed(1)}K`
  }
  return String(Math.round(value))
}
