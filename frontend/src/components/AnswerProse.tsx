import { formatAnswerParagraphs } from '../lib/answerFormatting'

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
        </p>
      ))}
    </div>
  )
}
