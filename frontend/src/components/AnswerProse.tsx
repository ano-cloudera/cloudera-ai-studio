import { formatAnswerParagraphs } from '../lib/answerFormatting'

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
  const paragraphs = formatAnswerParagraphs(text, { omitTables })
  if (!paragraphs.length) return null
  const resolvedVariant = variant ?? (emphasis ? 'main' : 'secondary')
  const paragraphClass = (index: number) => {
    if (resolvedVariant === 'main') {
      return index === 0 ? 'answer-prose-main' : 'answer-prose-support'
    }
    if (resolvedVariant === 'support') return 'answer-prose-support'
    return 'answer-prose-secondary'
  }
  return (
    <div className={`space-y-3 ${className}`}>
      {paragraphs.map((paragraph, index) => (
        <p key={index} className={`whitespace-pre-wrap ${paragraphClass(index)}`}>
          {paragraph.split('\n').map((line, lineIndex) => {
            const numbered = line.match(/^(\d+\.)\s+(.*)$/)
            if (numbered) {
              return (
                <span key={lineIndex} className="block pl-1">
                  <span className="font-medium text-slate-700">{numbered[1]}</span> {numbered[2]}
                </span>
              )
            }
            return (
              <span key={lineIndex} className="block">
                {line}
              </span>
            )
          })}
        </p>
      ))}
    </div>
  )
}
