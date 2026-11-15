/** Section names of an answer in the language of the question (the Backend sends it as `language`). */
const LABELS = {
  en: {
    insights: 'Insights',
    implications: 'Business implications',
    askNext: 'Want me to go further? Pick one',
    executiveSummary: 'Executive summary',
    comparison: 'Comparison',
    keyFindings: 'Key findings',
  },
  id: {
    insights: 'Temuan',
    implications: 'Implikasi bisnis',
    askNext: 'Mau saya lanjutkan? Pilih salah satu',
    executiveSummary: 'Ringkasan',
    comparison: 'Perbandingan',
    keyFindings: 'Temuan utama',
  },
} as const

export type AnswerSectionLabels = (typeof LABELS)[keyof typeof LABELS]

/** The platform's own words are English; the answer text itself follows the language of the question. */
export function answerSectionLabels(_language?: string | null): AnswerSectionLabels {
  return LABELS.en
}
