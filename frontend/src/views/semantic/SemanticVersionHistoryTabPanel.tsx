import type { SemanticRuntimeStatus, SemanticVersionRecord } from '../../types/api'
import { SemanticVersionHistoryTable } from './authoring/SemanticVersionHistoryTable'

type Props = {
  versions: SemanticVersionRecord[]
  runtimeStatus: SemanticRuntimeStatus | null
  saving: boolean
  onRollbackVersion: (v: SemanticVersionRecord) => void
}

export function SemanticVersionHistoryTabPanel({ versions, runtimeStatus, saving, onRollbackVersion }: Props) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid="semantic-version-history-tab-panel">
      <div className="border-b border-slate-100 px-4 py-3 text-sm text-slate-600">
        Registry and runtime versions for this semantic model. Roll back Ask Data to a prior version when needed.
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <SemanticVersionHistoryTable
          versions={versions}
          runtimeStatus={runtimeStatus}
          saving={saving}
          onRollback={onRollbackVersion}
        />
      </div>
    </div>
  )
}
