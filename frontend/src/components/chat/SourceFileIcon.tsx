import { File, FileSpreadsheet, FileText } from 'lucide-react'

export type SourceFileKind = 'pdf' | 'spreadsheet' | 'document' | 'text' | 'other'

export function sourceFileKind(filename: string | null | undefined): SourceFileKind {
  const ext = (filename ?? '').trim().split('.').pop()?.toLowerCase() ?? ''
  if (ext === 'pdf') return 'pdf'
  if (['xls', 'xlsx', 'csv', 'tsv'].includes(ext)) return 'spreadsheet'
  if (['doc', 'docx', 'rtf', 'odt'].includes(ext)) return 'document'
  if (['txt', 'md', 'markdown'].includes(ext)) return 'text'
  return 'other'
}

const TILE: Record<SourceFileKind, string> = {
  pdf: 'bg-red-50 text-red-600',
  spreadsheet: 'bg-emerald-50 text-emerald-600',
  document: 'bg-blue-50 text-blue-600',
  text: 'bg-slate-100 text-slate-600',
  other: 'bg-slate-100 text-slate-500',
}

type Props = {
  filename: string | null | undefined
  /** Tile size in pixels; the glyph scales with it. */
  size?: number
}

/** A tinted file tile: PDF red, spreadsheet/CSV green, Word-style documents blue, plain text and others grey. */
export function SourceFileIcon({ filename, size = 32 }: Props) {
  const kind = sourceFileKind(filename)
  const glyph = Math.round(size * 0.5)
  return (
    <span
      data-testid="source-file-icon"
      data-kind={kind}
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center rounded-lg ${TILE[kind]}`}
      style={{ width: size, height: size }}
    >
      {kind === 'pdf' ? (
        <span className="font-bold leading-none tracking-tight" style={{ fontSize: Math.max(9, Math.round(size * 0.3)) }}>
          PDF
        </span>
      ) : kind === 'spreadsheet' ? (
        <FileSpreadsheet size={glyph} />
      ) : kind === 'document' || kind === 'text' ? (
        <FileText size={glyph} />
      ) : (
        <File size={glyph} />
      )}
    </span>
  )
}
