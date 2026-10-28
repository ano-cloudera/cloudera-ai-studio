'use client'

import { Bot } from 'lucide-react'
import { useState } from 'react'
import { usePublicBranding } from '../config/PublicBrandingContext'

export function BrandMark() {
  const [failed, setFailed] = useState(false)
  const branding = usePublicBranding()
  const src = branding.logoUrl.trim()

  return (
    <div className="flex min-w-0 items-center gap-2.5">
      {!src || failed ? (
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-cloudera-navy">
          <Bot size={18} strokeWidth={1.5} aria-hidden />
        </div>
      ) : (
        <img
          src={src}
          alt=""
          aria-hidden
          className="h-8 w-8 shrink-0 object-contain"
          onError={() => setFailed(true)}
        />
      )}
      <span className="min-w-0 truncate text-[1.0625rem] font-medium leading-none text-cloudera-navy">
        {branding.sidebarBrandTitle}
      </span>
    </div>
  )
}
