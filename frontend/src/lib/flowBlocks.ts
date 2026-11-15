/**
 * Whether a paragraph of an answer is a sequence worth drawing as a flow: numbered steps (three or more, in order), or action lines
 * that hand work over with arrows ("Owner → action → deadline"). Anything else stays text. Only the layout is decided here; the
 * words are the answer's own.
 */
export type FlowBlock =
  | { kind: 'steps'; items: string[] }
  | { kind: 'handoffs'; rows: string[][] }

const NUMBERED = /^\s*\d{1,2}[.)]\s+(.*)$/
const BULLET = /^\s*[-•*]\s+(.*)$/
const ARROW = /\s+(?:→|->)\s+/

export function flowBlock(text: string): FlowBlock | null {
  const lines = (text ?? '').split('\n').map(line => line.trimEnd()).filter(line => line.trim())
  if (lines.length === 0) return null
  const numbered = lines.map(line => line.match(NUMBERED)?.[1]?.trim())
  if (lines.length >= 3 && numbered.every(Boolean)) return { kind: 'steps', items: numbered as string[] }
  const bullets = lines.map(line => line.match(BULLET)?.[1]?.trim())
  if (bullets.every(Boolean) && bullets.every(item => ARROW.test(item as string))) {
    return { kind: 'handoffs', rows: (bullets as string[]).map(item => item.split(ARROW).map(part => part.trim()).filter(Boolean)) }
  }
  return null
}
