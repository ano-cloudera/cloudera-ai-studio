// A plain "S" monogram avatar for SCAN, standing in for a generic
// sparkle/robot icon (lucide's Sparkles/Bot) that reads as "AI tool
// template" rather than a specific product. Matches the same monogram
// pattern already used for the user's own avatar ("AD") and the collapsed
// sidebar brand mark ("TS"), so the assistant looks like part of this
// product rather than a bolted-on AI widget.
export function ScanMark({ size = 32, rounded = 'xl', className = '' }: { size?: number; rounded?: 'lg' | 'xl' | '2xl'; className?: string }) {
  const roundedClass = { lg: 'rounded-lg', xl: 'rounded-xl', '2xl': 'rounded-2xl' }[rounded]
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center ${roundedClass} bg-cloudera-navy font-black text-white ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.42 }}
    >
      S
    </span>
  )
}
