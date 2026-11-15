import type { ReactNode } from 'react'

import type { FlowBlock } from '../lib/flowBlocks'

function Arrow({ direction }: { direction: 'down' | 'right' }) {
  return direction === 'down' ? (
    <svg width="14" height="22" viewBox="0 0 14 22" aria-hidden className="mx-auto shrink-0 text-cloudera-orange">
      <path d="M7 0v17M2 12l5 6 5-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg width="22" height="14" viewBox="0 0 22 14" aria-hidden className="shrink-0 text-cloudera-orange">
      <path d="M0 7h17M12 2l6 5-6 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** A procedure drawn as boxes joined by arrows: numbered steps go down the page, hand-overs (who, what, by when) go across. */
export function FlowDiagram({ block, renderText, textClass = '' }: { block: FlowBlock; renderText: (text: string) => ReactNode; textClass?: string }) {
  if (block.kind === 'steps') {
    return (
      <ol className={`m-0 list-none p-0 ${textClass}`} data-testid="flow-diagram" aria-label="Flow">
        {block.items.map((item, index) => (
          <li key={index} className="flex flex-col">
            <div className="flex items-start gap-3 rounded-lg border border-violet-100 bg-white px-3 py-2.5 shadow-[0_1px_2px_rgba(36,19,95,0.04)]">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cloudera-violet text-xs font-bold text-white">{index + 1}</span>
              <span className="min-w-0 text-slate-700">{renderText(item)}</span>
            </div>
            {index < block.items.length - 1 ? <Arrow direction="down" /> : null}
          </li>
        ))}
      </ol>
    )
  }
  return (
    <ul className={`m-0 list-none space-y-2 p-0 ${textClass}`} data-testid="flow-diagram" aria-label="Flow">
      {block.rows.map((row, index) => (
        <li key={index} className="flex flex-wrap items-center gap-2">
          {row.map((part, partIndex) => (
            <span key={partIndex} className="flex items-center gap-2">
              <span
                className={
                  partIndex === 0 && row.length > 1
                    ? 'rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 font-semibold text-cloudera-violet'
                    : partIndex === row.length - 1 && row.length > 2
                      ? 'rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-slate-700'
                      : 'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-slate-700'
                }
              >
                {renderText(part)}
              </span>
              {partIndex < row.length - 1 ? <Arrow direction="right" /> : null}
            </span>
          ))}
        </li>
      ))}
    </ul>
  )
}
