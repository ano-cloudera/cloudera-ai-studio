const percentagePattern = /([+-]?\d+(?:\.\d+)?)%/g
const monetaryPhrasePattern = /\b(dari|menjadi|from|to|adalah|hingga|of|is|nilai)\s+(-?\d+(?:\.\d{3,})?)/gi

export function formatFloatingAnswerText(text: string): string {
  const containsRawComparison = /\b(?:current_value|previous_value|absolute_change|percentage_change)\s*=/i.test(text)
  const formatted = text
    .replace(/\bcurrent_value\s*=\s*(-?\d+(?:\.\d+)?)/gi, (_, raw: string) => `Current sales: ${formatMillionIdr(Number(raw))}`)
    .replace(/\bprevious_value\s*=\s*(-?\d+(?:\.\d+)?)/gi, (_, raw: string) => `Previous period: ${formatMillionIdr(Number(raw))}`)
    .replace(/\babsolute_change\s*=\s*(-?\d+(?:\.\d+)?)/gi, (_, raw: string) => `Change: ${formatSignedMillionIdr(Number(raw))}`)
    .replace(/\bpercentage_change\s*=\s*(-?\d+(?:\.\d+)?)/gi, (_, raw: string) => `Change percentage: ${formatPercentage(Number(raw))}`)
  return (containsRawComparison ? formatted.replace(/;\s*/g, ' • ') : formatted)
    .replace(percentagePattern, (_, raw: string) => formatPercentage(Number(raw)))
    .replace(monetaryPhrasePattern, (_, prefix: string, raw: string) => `${prefix} ${formatMillionIdr(Number(raw))}`)
}

export function formatFloatingDriver(text: string): string {
  if (/^\s*Provenance:/i.test(text) && /\b(?:source_type|data_confidence)\s*=/i.test(text)) return ''
  const businessDescription = text.replace(/\s*Evidence:\s*.*$/i, '').trim()
  return formatFloatingAnswerText(businessDescription)
}

function formatPercentage(value: number): string {
  if (!Number.isFinite(value)) return 'Unavailable'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatMillionIdr(value: number): string {
  if (!Number.isFinite(value)) return 'Unavailable'
  const sign = value < 0 ? '-' : ''
  const absolute = Math.abs(value)
  if (absolute >= 1_000_000) return `${sign}Rp${(absolute / 1_000_000).toFixed(2)}T`
  if (absolute >= 1_000) return `${sign}Rp${(absolute / 1_000).toFixed(2)}B`
  return `${sign}Rp${absolute.toFixed(2)}M`
}

function formatSignedMillionIdr(value: number): string {
  const formatted = formatMillionIdr(value)
  return value > 0 ? `+${formatted}` : formatted
}
