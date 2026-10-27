import clsx from 'clsx'

export function StatusPill({ label, tone = 'green' }: { label: string; tone?: 'green' | 'orange' | 'violet' | 'red' }) {
  return <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold', {
    'bg-emerald-50 text-emerald-700': tone === 'green',
    'bg-orange-50 text-orange-700': tone === 'orange',
    'bg-violet-50 text-violet-700': tone === 'violet',
    'bg-red-50 text-red-700': tone === 'red',
  })}><span className="h-1.5 w-1.5 rounded-full bg-current" />{label}</span>
}
