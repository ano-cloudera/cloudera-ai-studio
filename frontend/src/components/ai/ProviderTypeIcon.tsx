import type { AiProviderType } from '../../types/api'

const ICON_BY_TYPE: Partial<Record<AiProviderType, string>> = {
  GEMINI: '/icons/ai/gemini.png',
  OPENAI: '/icons/ai/openai.png',
  OPENAI_COMPATIBLE: '/icons/ai/openai-compatible.jpg',
  ANTHROPIC: '/icons/ai/claude.png',
}

type Props = {
  providerType: AiProviderType | string
  size?: number
  className?: string
}

export function ProviderTypeIcon({ providerType, size = 20, className = '' }: Props) {
  const key = String(providerType).toUpperCase() as AiProviderType
  const src = ICON_BY_TYPE[key]
  if (!src) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-md bg-slate-100 text-[10px] font-bold text-slate-500 ${className}`}
        style={{ width: size, height: size }}
        aria-hidden
      >
        AI
      </span>
    )
  }
  return (
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      className={`inline-block shrink-0 rounded-sm object-contain ${className}`}
    />
  )
}
