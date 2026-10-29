const TABLE_PATTERN = /\b(?:gold|silver|bronze)\.[a-z0-9_]+/gi

export type DataProvenance = {
  note: string | null
  sources: string[]
}

// A reference that is only a table identifier ("default.credit_applications", "hive.default.t"), as written for
// connector-backed models, whose schema is not one of the legacy gold/silver/bronze layers.
const BARE_TABLE_PATTERN = /^`?"?[a-z_][a-z0-9_]*"?`?(?:\.`?"?[a-z_][a-z0-9_]*"?`?){1,2}$/i

function uniqueTables(value: string): string[] {
  const matches = value.match(TABLE_PATTERN) ?? []
  if (!matches.length && BARE_TABLE_PATTERN.test(value.trim())) {
    return [value.trim().replace(/[`"]/g, '').toLowerCase()]
  }
  return [...new Set(matches.map(item => item.toLowerCase()))]
}

function proseWithoutSql(value: string): string {
  const match = value.match(/^(.*?)(?:query:\s*)(select[\s\S]+)$/i)
  return (match ? match[1] : value).trim()
}

function proseWithoutTables(prose: string, tables: string[]): string | null {
  let note = prose
  for (const table of tables) {
    note = note.replace(new RegExp(table.replace('.', '\\.'), 'gi'), '').trim()
  }
  note = note.replace(/^[,;:\s\-–]+|[,;:\s\-–]+$/g, '').trim()
  if (!note || note.length < 8) return null
  return note
}

const INTERNAL_DATA_REF =
  /^(clarification_required|ask_data_scope|explicit structured context|no query result was used\.?|retrieved document evidence|mcp:.*)$/i

export function parseDataProvenance(dataReference: string | null | undefined): DataProvenance | null {
  if (!dataReference?.trim()) return null
  const raw = dataReference.trim()
  if (/no governed query result attached/i.test(raw)) return null
  if (INTERNAL_DATA_REF.test(raw)) return null

  const sources = uniqueTables(raw)
  const prose = proseWithoutSql(raw)
  let note = proseWithoutTables(prose, sources)

  if (!note && sources.length === 0 && prose.length >= 8) {
    note = prose
  }

  if (!note && sources.length === 0) return null
  return { note, sources }
}

const INTERNAL_CAVEAT =
  /^(metric_ambiguous|clarification_required|explicit_context_unavailable|unsupported_dimension|insufficient_context)$/i

export function mergeDataNotes(
  caveats: string[],
  provenance: DataProvenance | null,
  options?: { hideInternalCodes?: boolean },
): string | null {
  let parts = [...caveats.map(item => item.trim()).filter(Boolean)]
  if (options?.hideInternalCodes) {
    parts = parts.filter(item => !INTERNAL_CAVEAT.test(item))
  }
  if (provenance?.note && !parts.some(part => part.includes(provenance.note!))) {
    parts.unshift(provenance.note)
  }
  if (!parts.length) return null
  return parts.join(' ')
}
