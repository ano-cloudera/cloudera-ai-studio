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

export type AnswerBlock =
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'table'; header: string[]; rows: string[][] }

const TABLE_SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/
const HEADING = /^#{1,4}\s+(.*)$/

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
}

/**
 * The answer as blocks: sub-headings, paragraphs (lists stay inside a paragraph) and small markdown tables, the way a written
 * report is laid out. `omitTables` drops tables when the same rows are already shown in the data grid.
 */
export function answerBlocks(text: string, options?: { omitTables?: boolean }): AnswerBlock[] {
  const body = (text ?? '').trim()
  if (!body) return []
  const lines = body.split('\n')
  const blocks: AnswerBlock[] = []
  let paragraph: string[] = []
  const flush = () => {
    const joined = paragraph.join('\n').trim()
    if (joined) blocks.push({ kind: 'paragraph', text: joined })
    paragraph = []
  }
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (!line.trim()) {
      flush()
      continue
    }
    const heading = line.match(HEADING)
    if (heading) {
      flush()
      blocks.push({ kind: 'heading', text: heading[1].trim() })
      continue
    }
    if (TABLE_LINE.test(line) && i + 1 < lines.length && TABLE_SEPARATOR.test(lines[i + 1])) {
      flush()
      const header = tableCells(line)
      const rows: string[][] = []
      let j = i + 2
      while (j < lines.length && TABLE_LINE.test(lines[j])) {
        rows.push(tableCells(lines[j]))
        j += 1
      }
      i = j - 1
      if (!options?.omitTables) blocks.push({ kind: 'table', header, rows })
      continue
    }
    if (options?.omitTables && TABLE_LINE.test(line)) continue
    paragraph.push(line)
  }
  flush()
  return blocks
}

export function truncateAxisLabel(value: unknown, max = 16): string {
  const label = String(value ?? '')
  if (label.length <= max) return label
  return `${label.slice(0, max - 1)}…`
}
