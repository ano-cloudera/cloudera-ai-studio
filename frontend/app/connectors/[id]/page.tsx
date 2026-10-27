import { Suspense } from 'react'
import { ConnectorDetailPage } from '../../../src/views/ConnectorDetailPage'

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return (
    <Suspense fallback={<div className="p-8 text-sm text-slate-600">Loading…</div>}>
      <ConnectorDetailPage connectorId={id} />
    </Suspense>
  )
}
