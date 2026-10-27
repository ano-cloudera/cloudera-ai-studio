import { Suspense } from 'react'
import { AskDataPage } from '../src/views/AskDataPage'

export default function Page() {
  return (
    <Suspense fallback={null}>
      <AskDataPage />
    </Suspense>
  )
}
