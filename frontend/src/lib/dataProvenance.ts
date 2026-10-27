const TABLE_PATTERN = /\b(?:gold|silver|bronze)\.[a-z0-9_]+/gi

export type DataProvenance = {
  note: string | null
  sources: string[]
}

function uniqueTables(value: string): string[] {
  const matches = value.match(TABLE_PATTERN) ?? []
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

export function parseDataProvenance(dataReference: string | null | undefined): DataProvenance | null {
  if (!dataReference?.trim()) return null
  const raw = dataReference.trim()
  if (/no governed query result attached/i.test(raw)) return null

  const sources = uniqueTables(raw)
  const prose = proseWithoutSql(raw)
  let note = proseWithoutTables(prose, sources)

  if (!note && sources.length === 0 && prose.length >= 8) {
    note = prose
  }

  if (!note && sources.length === 0) return null
  return { note, sources }
}

export function mergeDataNotes(caveats: string[], provenance: DataProvenance | null): string | null {
  const parts = [...caveats.map(item => item.trim()).filter(Boolean)]
  if (provenance?.note && !parts.some(part => part.includes(provenance.note!))) {
    parts.unshift(provenance.note)
  }
  if (!parts.length) return null
  return parts.join(' ')
}
