'use client'

import { useMemo } from 'react'
import hljs from 'highlight.js/lib/core'
import sqlLang from 'highlight.js/lib/languages/sql'
import 'highlight.js/styles/vs2015.css'

hljs.registerLanguage('sql', sqlLang)

type Props = {
  sql: string
  wrapLines: boolean
}

export function WorkspaceSqlBlock({ sql, wrapLines }: Props) {
  const html = useMemo(() => {
    try {
      return hljs.highlight(sql, { language: 'sql' }).value
    } catch {
      return hljs.highlightAuto(sql).value
    }
  }, [sql])

  return (
    <pre
      className={`workspace-sql-block max-h-80 overflow-auto rounded-xl border border-slate-800 p-4 text-[13px] leading-relaxed ${
        wrapLines ? 'whitespace-pre-wrap break-words' : 'whitespace-pre overflow-x-auto'
      }`}
    >
      <code className="hljs language-sql !bg-transparent !p-0" dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  )
}
