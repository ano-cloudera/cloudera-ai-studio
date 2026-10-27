import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

function formatValue(value: string | number, format: string) {
  if (typeof value === 'string') return value
  if (format === 'percent') return `${value.toFixed(1)}%`
  if (format === 'currency_idr') {
    if (Math.abs(value) >= 1_000_000_000_000) return `Rp ${(value / 1_000_000_000_000).toFixed(2)}T`
    if (Math.abs(value) >= 1_000_000_000) return `Rp ${(value / 1_000_000_000).toFixed(2)}B`
    if (Math.abs(value) >= 1_000_000) return `Rp ${(value / 1_000_000).toFixed(1)}M`
    return `Rp ${value.toLocaleString('id-ID', { maximumFractionDigits: 2 })}`
  }
  if (format === 'currency_billion') {
    if (value >= 1_000_000) return `Rp ${(value / 1_000_000).toFixed(2)}T`
    if (value >= 1_000) return `Rp ${(value / 1_000).toFixed(1)}B`
    return `Rp ${value.toFixed(0)}M`
  }
  if (format === 'score') return value.toFixed(1)
  return value.toLocaleString()
}

export function KpiCard({ label, value, format, delta, icon: Icon, highlighted = false, context = '' }: any) {
  const positive = typeof delta === 'number' && delta >= 0
  const available = (typeof value === 'number' && Number.isFinite(value)) || (typeof value === 'string' && value.trim())
  return (
    <div className={`card p-4 ${highlighted ? 'border-orange-300 ring-2 ring-orange-100' : ''}`}>
      <div className="flex items-start justify-between">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-violet-50 text-cloudera-violet"><Icon size={16} strokeWidth={2} /></div>
        {typeof delta === 'number' && <span className={`flex items-center gap-1 text-xs font-bold ${positive ? 'text-emerald-600' : 'text-rose-600'}`}>{positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{Math.abs(delta).toFixed(1)}%</span>}
      </div>
      <div className="mt-3 text-xs font-bold text-slate-500">{label}</div>
      <div className={`mt-1 truncate font-black tracking-tight ${available ? 'text-2xl text-cloudera-navy' : 'text-base text-slate-400'}`}>{available ? formatValue(value, format) : 'Not available'}</div>
      {context && <div className="mt-1 truncate text-xs text-slate-400" title={context}>{context}</div>}
    </div>
  )
}
