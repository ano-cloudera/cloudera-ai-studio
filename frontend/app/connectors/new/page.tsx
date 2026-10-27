import { Suspense } from 'react'
import { ConnectorCreatePage } from '../../../src/views/ConnectorCreatePage'

export default function Page() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-slate-600">Loading…</div>}>
      <ConnectorCreatePage />
    </Suspense>
  )
}
