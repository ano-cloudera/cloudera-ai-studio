import { answerBlocks } from '../lib/answerFormatting'

/** `**bold**` only; everything else stays plain text (no HTML is ever interpreted). */
function renderInline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={index} className="font-semibold text-slate-900">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  )
}

function ProseLines({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, lineIndex) => {
        const numbered = line.match(/^(\d+\.)\s+(.*)$/)
        if (numbered) {
          return (
            <span key={lineIndex} className="block pl-1">
              <span className="font-medium text-slate-700">{numbered[1]}</span> {renderInline(numbered[2] ?? '')}
            </span>
          )
        }
        const bullet = line.match(/^\s*[-•*]\s+(.*)$/)
        if (bullet) {
          return (
            <span key={lineIndex} className="flex gap-2 pl-1">
              <span className="mt-[0.55em] h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" aria-hidden />
              <span className="min-w-0">{renderInline(bullet[1] ?? '')}</span>
            </span>
          )
        }
        return (
          <span key={lineIndex} className="block">
            {renderInline(line)}
          </span>
        )
      })}
    </>
  )
}

export function AnswerProse({
  text,
  omitTables = false,
  className = '',
  emphasis = false,
  variant,
}: {
  text: string
  omitTables?: boolean
  className?: string
  emphasis?: boolean
  /** Typography within `.chat-response-typography` only. */
  variant?: 'main' | 'support' | 'secondary'
}) {
  const blocks = answerBlocks(text, { omitTables })
  if (!blocks.length) return null
  const resolvedVariant = variant ?? (emphasis ? 'main' : 'secondary')
  let paragraphIndex = -1
  const paragraphClass = () => {
    paragraphIndex += 1
    if (resolvedVariant === 'main') {
      return paragraphIndex === 0 ? 'answer-prose-main' : 'answer-prose-support'
    }
    if (resolvedVariant === 'support') return 'answer-prose-support'
    return 'answer-prose-secondary'
  }
  return (
    <div className={`space-y-3 ${className}`}>
      {blocks.map((block, index) => {
        if (block.kind === 'heading') {
          return (
            <h4 key={index} className="answer-prose-heading pt-1 text-sm font-semibold text-slate-900">
              {renderInline(block.text)}
            </h4>
          )
        }
        if (block.kind === 'table') {
          return (
            <div key={index} className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="answer-prose-table min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-700">
                  <tr>
                    {block.header.map((cell, cellIndex) => (
                      <th key={cellIndex} scope="col" className="px-3 py-2 font-semibold">
                        {renderInline(cell)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {block.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {block.header.map((_, cellIndex) => (
                        <td key={cellIndex} className="px-3 py-2 align-top">
                          {renderInline(row[cellIndex] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
        return (
          <p key={index} className={`whitespace-pre-wrap ${paragraphClass()}`}>
            <ProseLines text={block.text} />
          </p>
        )
      })}
    </div>
  )
}
