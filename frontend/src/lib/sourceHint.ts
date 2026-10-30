export type SourceHint = 'mcp' | 'knowledge'

const MCP_SUBJECT = /\b(applicant|assess|likelihood)\b/i
const MCP_INPUTS = /\b(dti|credit score)\b/i
const KNOWLEDGE_QUESTION =
  /\b(when does|what (?:are|is) the (?:standard )?(?:approval )?(?:criteria|policy|threshold)|what does the .+ (?:say|require)|according to the)\b/i

/**
 * Questions are answered by the attached source (no chip = Ask Data). Suggest a chip only for
 * wording that clearly belongs to a model tool or to the documents, so Ask Data questions that
 * merely mention "policy" or "credit score" are left alone.
 */
export function suggestSourceHint(question: string, hasContext: boolean): SourceHint | null {
  const text = question.trim()
  if (hasContext || text.length < 12) return null
  if (/\d/.test(text) && MCP_INPUTS.test(text) && MCP_SUBJECT.test(text)) return 'mcp'
  if (KNOWLEDGE_QUESTION.test(text)) return 'knowledge'
  return null
}

export function sourceHintMessage(hint: SourceHint): string {
  return hint === 'mcp'
    ? 'This looks like an applicant assessment. Type @ and attach the credit risk model to get the model result.'
    : 'This looks like a question for your documents. Type @ and attach a knowledge library to answer from them.'
}
