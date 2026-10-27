import { Suspense } from 'react'
import { EditorDirtyProvider } from '../../src/views/semantic/authoring/EditorDirtyContext'
import { SemanticLayerPage } from '../../src/views/SemanticLayerPage'

export default function Page() {
  return (
    <EditorDirtyProvider>
      <Suspense fallback={null}>
        <SemanticLayerPage />
      </Suspense>
    </EditorDirtyProvider>
  )
}
