'use client'

import { useMemo } from 'react'
import { formatSql, tokenizeLine, type SqlTokenKind } from '../../lib/formatSql'

type Props = {
  sql: string
  wrapLines: boolean
}

// A dark editor palette: keywords blue, functions yellow, strings orange, numbers green, quoted names light blue.
const COLOURS: Record<SqlTokenKind, string> = {
  keyword: 'text-[#569CD6]',
  function: 'text-[#DCDCAA]',
  string: 'text-[#CE9178]',
  number: 'text-[#B5CEA8]',
  identifier: 'text-[#D4D4D4]',
  comment: 'text-[#6A9955]',
  operator: 'text-[#D4D4D4]',
  punct: 'text-[#D4D4D4]',
  space: '',
}

/** The query as a developer would read it: laid out one clause per line, numbered, coloured. The words are the ones that ran. */
export function WorkspaceSqlBlock({ sql, wrapLines }: Props) {
  const lines = useMemo(() => formatSql(sql).split('\n'), [sql])
  const gutter = String(lines.length).length

  return (
    <div
      className="workspace-sql-block max-h-[28rem] overflow-auto rounded-lg border border-slate-800 py-3 font-mono text-[13px] leading-6"
      role="region"
      aria-label="SQL"
      data-testid="workspace-sql"
    >
      <ol className={`min-w-full ${wrapLines ? '' : 'w-max'}`}>
        {lines.map((line, index) => (
          <li key={index} className="flex">
            <span
              aria-hidden
              className="sticky left-0 shrink-0 select-none bg-[#1e1e1e] pl-3 pr-3 text-right text-[#6E7681]"
              style={{ minWidth: `${gutter + 2}ch` }}
            >
              {index + 1}
            </span>
            <code className={`min-w-0 flex-1 pr-4 ${wrapLines ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'}`}>
              {tokenizeLine(line).map((token, at) => (
                <span key={at} className={COLOURS[token.kind]}>
                  {token.text}
                </span>
              ))}
            </code>
          </li>
        ))}
      </ol>
    </div>
  )
}
