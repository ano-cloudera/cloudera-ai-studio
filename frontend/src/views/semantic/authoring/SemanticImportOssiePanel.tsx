'use client'

import type { OssieImportSource, OssieImportSummary } from '../../../types/api'

type Props = {
  importSource: OssieImportSource | null
  importKey: string
  onImportKeyChange: (v: string) => void
  importSummary: OssieImportSummary | null
  saving: boolean
  onImport: () => void
}

export function SemanticImportOssiePanel(props: Props) {
  return (
    <div className="space-y-4 p-4 text-sm" data-testid="semantic-import-ossie-panel">
      <div>
        <h2 className="text-sm font-semibold text-cloudera-navy">Import OSSIE</h2>
        <p className="mt-1 text-xs text-slate-600">
          Imports as DRAFT via registry API. Does not modify on-disk OSSIE files.
        </p>
      </div>
      {props.importSource ? (
        <p className="text-xs text-slate-500">
          Source: {props.importSource.ossie_file} {props.importSource.exists ? '' : '(missing)'}
        </p>
      ) : null}
      <label className="block text-xs font-semibold text-slate-600">
        Semantic model key
        <input
          className="mt-1 w-full max-w-md rounded-lg border border-slate-200 px-3 py-2 text-sm"
          value={props.importKey}
          onChange={e => props.onImportKeyChange(e.target.value)}
        />
      </label>
      {props.importSummary ? (
        <div className="max-w-lg rounded-lg bg-slate-50 p-3 text-xs">
          <div>
            Imported: {props.importSummary.imported.entities} entities, {props.importSummary.imported.metrics} metrics,{' '}
            {props.importSummary.imported.dimensions} dimensions
          </div>
          {props.importSummary.warnings.map(w => (
            <div key={w} className="text-amber-800">
              {w}
            </div>
          ))}
          {props.importSummary.errors.map(e => (
            <div key={e} className="text-red-800">
              {e}
            </div>
          ))}
        </div>
      ) : null}
      <button
        type="button"
        data-testid="semantic-import-ossie-submit"
        className="btn-primary h-9 px-3 text-sm"
        disabled={props.saving}
        onClick={props.onImport}
      >
        Import as draft
      </button>
    </div>
  )
}
