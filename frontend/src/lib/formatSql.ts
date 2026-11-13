/**
 * A small SQL formatter and tokenizer for showing the query that ran, laid out the way a query editor would: one clause per
 * line, one selected column per line, one condition per line, sub-queries indented. It only changes whitespace and never the
 * words, so the text copied is the query that ran. No dependency: the governed queries are plain SELECTs.
 */

export type SqlTokenKind = 'keyword' | 'function' | 'string' | 'number' | 'identifier' | 'comment' | 'operator' | 'punct' | 'space'

export type SqlToken = { kind: SqlTokenKind; text: string }

const KEYWORDS = new Set(
  (
    'SELECT FROM WHERE GROUP BY ORDER HAVING LIMIT OFFSET UNION ALL DISTINCT AS ON JOIN LEFT RIGHT INNER OUTER FULL CROSS WITH ' +
    'AND OR NOT IN IS NULL LIKE BETWEEN CASE WHEN THEN ELSE END ASC DESC CAST OVER PARTITION INTERVAL TRUE FALSE EXISTS ANY SOME ' +
    'DATE TIMESTAMP USING FETCH FIRST ROWS ONLY'
  ).split(' '),
)

/** Words that start a new line at the level of the statement they belong to. */
const CLAUSES = ['SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET', 'UNION ALL', 'UNION', 'WITH']
const JOINS = ['LEFT OUTER JOIN', 'RIGHT OUTER JOIN', 'FULL OUTER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'CROSS JOIN', 'FULL JOIN', 'JOIN']

type Raw = { text: string; kind: 'word' | 'string' | 'quoted' | 'number' | 'comment' | 'punct' | 'operator' }

function scan(sql: string): Raw[] {
  const out: Raw[] = []
  let i = 0
  while (i < sql.length) {
    const ch = sql[i]
    if (/\s/.test(ch)) {
      i += 1
    } else if (ch === '-' && sql[i + 1] === '-') {
      const end = sql.indexOf('\n', i)
      const stop = end === -1 ? sql.length : end
      out.push({ text: sql.slice(i, stop), kind: 'comment' })
      i = stop
    } else if (ch === "'" || ch === '"' || ch === '`') {
      let j = i + 1
      while (j < sql.length) {
        if (sql[j] === ch) {
          if (sql[j + 1] === ch) j += 2
          else break
        } else j += 1
      }
      out.push({ text: sql.slice(i, j + 1), kind: ch === "'" ? 'string' : 'quoted' })
      i = j + 1
    } else if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(sql[i + 1] ?? ''))) {
      let j = i + 1
      while (j < sql.length && /[0-9.eE]/.test(sql[j])) j += 1
      out.push({ text: sql.slice(i, j), kind: 'number' })
      i = j
    } else if (/[A-Za-z_]/.test(ch)) {
      let j = i + 1
      while (j < sql.length && /[A-Za-z0-9_$]/.test(sql[j])) j += 1
      out.push({ text: sql.slice(i, j), kind: 'word' })
      i = j
    } else if ('(),;.'.includes(ch)) {
      out.push({ text: ch, kind: 'punct' })
      i += 1
    } else {
      let j = i + 1
      while (j < sql.length && '<>=!|+-*/%'.includes(sql[j]) && '<>=!|+-*/%'.includes(ch)) j += 1
      out.push({ text: sql.slice(i, j), kind: 'operator' })
      i = j
    }
  }
  return out
}

const INDENT = '  '

type Item = { text: string }

/** Index of the parenthesis that closes the one opened at `open`. */
function closing(raw: Raw[], open: number): number {
  let depth = 0
  for (let i = open; i < raw.length; i += 1) {
    if (raw[i].kind === 'punct' && raw[i].text === '(') depth += 1
    if (raw[i].kind === 'punct' && raw[i].text === ')') {
      depth -= 1
      if (depth === 0) return i
    }
  }
  return raw.length - 1
}

function upper(raw: Raw): string {
  return raw.text.toUpperCase()
}

/** Whether the words starting at `at` spell one of `phrases` (two-word clauses such as GROUP BY); the phrase, else null. */
function phraseAt(raw: Raw[], at: number, phrases: string[]): string | null {
  for (const phrase of phrases) {
    const words = phrase.split(' ')
    if (words.every((word, offset) => raw[at + offset]?.kind === 'word' && upper(raw[at + offset]) === word)) return phrase
  }
  return null
}

/** Joins raw tokens into one line of text with the spacing a person would write. */
function inline(raw: Raw[]): string {
  let text = ''
  raw.forEach((token, index) => {
    const prev = raw[index - 1]
    const noSpaceBefore = token.text === ',' || token.text === ')' || token.text === '.' || token.text === ';'
    const noSpaceAfterPrev = !prev || prev.text === '(' || prev.text === '.'
    const callParen = token.text === '(' && prev?.kind === 'word' && !KEYWORDS.has(upper(prev))
    const castParen = token.text === '(' && prev?.kind === 'word' && ['CAST', 'IN', 'OVER'].includes(upper(prev)) && upper(prev) !== 'IN'
    text += !text || noSpaceBefore || noSpaceAfterPrev || callParen || castParen ? token.text : ` ${token.text}`
  })
  return text
}

function formatRange(raw: Raw[], start: number, end: number, level: number): string[] {
  const lines: string[] = []
  let current: Raw[] = []
  let indent = 0 // the indent of the line being built, in levels from `level`
  let clause = ''
  let betweenPending = false
  const flush = () => {
    if (current.length) lines.push(`${INDENT.repeat(level + indent)}${inline(current)}`)
    current = []
  }
  const begin = (nextIndent: number) => {
    flush()
    indent = nextIndent
  }
  let i = start
  while (i <= end) {
    const token = raw[i]
    const atTop = depthAt(raw, start, i) === 0
    if (token.kind === 'word' && atTop) {
      const join = phraseAt(raw, i, JOINS)
      const clauseWord = join ? null : phraseAt(raw, i, CLAUSES)
      if (join || clauseWord) {
        const phrase = (join ?? clauseWord) as string
        const words = raw.slice(i, i + phrase.split(' ').length)
        clause = join ? 'JOIN' : phrase
        begin(0)
        current = words
        i += words.length
        if (clause === 'SELECT' || clause === 'WHERE' || clause === 'HAVING') {
          // The header stands alone; what it holds goes one level in, a line each.
          begin(1)
        }
        continue
      }
      if ((clause === 'WHERE' || clause === 'HAVING' || clause === 'JOIN') && ['AND', 'OR'].includes(upper(token))) {
        if (betweenPending && upper(token) === 'AND') {
          betweenPending = false
          current.push(token)
        } else {
          begin(1)
          current = [token]
        }
        i += 1
        continue
      }
      if (upper(token) === 'BETWEEN') betweenPending = true
    }
    if (token.kind === 'punct' && token.text === '(') {
      const close = closing(raw, i)
      const inner = raw.slice(i + 1, close)
      if (inner.length && inner[0].kind === 'word' && ['SELECT', 'WITH'].includes(upper(inner[0]))) {
        // A sub-query: opened on this line, its own lines one level in, closed on a line of its own.
        const opened = indent
        current.push(token)
        flush()
        lines.push(...formatRange(raw, i + 1, close - 1, level + opened + 1))
        indent = opened
        current = [raw[close]]
        i = close + 1
        continue
      }
    }
    if (token.kind === 'punct' && token.text === ',' && atTop && (clause === 'SELECT' || clause === 'GROUP BY' || clause === 'ORDER BY')) {
      current.push(token)
      begin(1)
      i += 1
      continue
    }
    current.push(token)
    i += 1
  }
  flush()
  return lines
}

function depthAt(raw: Raw[], start: number, at: number): number {
  let depth = 0
  for (let i = start; i < at; i += 1) {
    if (raw[i].kind === 'punct' && raw[i].text === '(') depth += 1
    if (raw[i].kind === 'punct' && raw[i].text === ')') depth -= 1
  }
  return depth
}

/** The query laid out one clause per line; the same words, only whitespace changed. */
export function formatSql(sql: string): string {
  const raw = scan(sql.trim().replace(/;\s*$/, ''))
  if (!raw.length) return sql.trim()
  const lines = formatRange(raw, 0, raw.length - 1, 0)
  return lines.filter(line => line.trim().length > 0).join('\n')
}

/** Tokens of one line of formatted SQL, for colouring. */
export function tokenizeLine(line: string): SqlToken[] {
  const tokens: SqlToken[] = []
  const lead = line.match(/^\s*/)?.[0] ?? ''
  if (lead) tokens.push({ kind: 'space', text: lead })
  const raw = scan(line.slice(lead.length))
  const rest = line.slice(lead.length)
  // `scan` drops whitespace, so it is put back from the source between tokens.
  let cursor = 0
  raw.forEach((token, index) => {
    const at = rest.indexOf(token.text, cursor)
    if (at > cursor) tokens.push({ kind: 'space', text: rest.slice(cursor, at) })
    cursor = at + token.text.length
    let kind: SqlTokenKind
    if (token.kind === 'string') kind = 'string'
    else if (token.kind === 'quoted') kind = 'identifier'
    else if (token.kind === 'number') kind = 'number'
    else if (token.kind === 'comment') kind = 'comment'
    else if (token.kind === 'operator') kind = 'operator'
    else if (token.kind === 'punct') kind = 'punct'
    else if (KEYWORDS.has(token.text.toUpperCase())) kind = 'keyword'
    else if (raw[index + 1]?.text === '(') kind = 'function'
    else kind = 'identifier'
    tokens.push({ kind, text: token.text })
  })
  if (cursor < rest.length) tokens.push({ kind: 'space', text: rest.slice(cursor) })
  return tokens
}
