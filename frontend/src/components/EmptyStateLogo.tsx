'use client'

import { Bot } from 'lucide-react'
import { useState } from 'react'
import { appConfig } from '../config/appConfig'

const WRAPPER_CLASS =
  'mx-auto flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-slate-200/70 bg-white shadow-[0_1px_4px_rgba(36,19,95,0.07)] h-14 w-14 sm:h-[72px] sm:w-[72px] md:h-20 md:w-20'

const IMAGE_CLASS = 'h-11 w-11 object-contain sm:h-14 sm:w-14 md:h-[60px] md:w-[60px]'

type EmptyStateLogoProps = {
  className?: string
}

/** Config-driven product logo for Ask Data empty state; circular mark with generic fallback. */
export function EmptyStateLogo({ className = '' }: EmptyStateLogoProps) {
  const [failed, setFailed] = useState(false)
  const src = appConfig.branding.emptyStateLogo.trim()

  if (!src || failed) {
    return (
      <div className={`${WRAPPER_CLASS} ${className}`}>
        <Bot aria-hidden className="h-7 w-7 text-cloudera-navy/75 sm:h-8 sm:w-8" strokeWidth={1.5} />
      </div>
    )
  }

  return (
    <div className={`${WRAPPER_CLASS} ${className}`}>
      <img src={src} alt="" aria-hidden className={IMAGE_CLASS} onError={() => setFailed(true)} />
    </div>
  )
}
