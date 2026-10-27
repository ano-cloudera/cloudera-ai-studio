const TABLE_LINE = /^\s*\|/

export function stripMarkdownTables(text: string): string {
  const lines = text.split('\n')
  const kept: string[] = []
  let inTable = false
  for (const line of lines) {
    if (TABLE_LINE.test(line)) {
      inTable = true
      continue
    }
    if (inTable && /^\s*\|?\s*:?-{3,}/.test(line)) continue
    inTable = false
    kept.push(line)
  }
  return kept.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

/** Prose blocks for display (headings, lists) without duplicating grid data. */
export function formatAnswerParagraphs(text: string, options?: { omitTables?: boolean }): string[] {
  let body = text.trim()
  if (!body) return []
  if (options?.omitTables) body = stripMarkdownTables(body)
  body = body.replace(/^#{1,3}\s+/gm, '')
  return body
    .split(/\n{2,}/)
    .map(part => part.trim())
    .filter(Boolean)
}

export function truncateAxisLabel(value: unknown, max = 16): string {
  const label = String(value ?? '')
  if (label.length <= max) return label
  return `${label.slice(0, max - 1)}…`
}
