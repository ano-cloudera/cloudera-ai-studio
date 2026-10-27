'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { ConnectorTypeIcon } from '../components/connectors/ConnectorTypeIcon'
import { api } from '../lib/api'
import type { ConnectorType } from '../types/api'
import { CONNECTOR_TYPE_BLURBS, connectorTypeLabel, slugConnectorKey } from './connectors/connectorUi'
import {
  CREATE_DATA_SOURCE_TITLE,
  CREATE_DATA_SOURCE_TYPE_HINT,
  DATA_SOURCE_TYPE_LABEL,
  SAVE_DATA_SOURCE,
} from './connectors/dataSourceUx'
import { appConfig } from '../config/appConfig'
import {
  buildConfig,
  ConnectorTypeForm,
  defaultFormState,
  type ConnectorFormState,
} from './connectors/ConnectorFormFields'

const TYPES: ConnectorType[] = ['impala', 'trino', 'postgres']

export function ConnectorCreatePage() {
  const router = useRouter()
  const params = useSearchParams()
  const typeParam = params.get('type') as ConnectorType | null
  const [selectedType, setSelectedType] = useState<ConnectorType | null>(
    typeParam && TYPES.includes(typeParam) ? typeParam : null,
  )
  const [form, setForm] = useState<ConnectorFormState>(() =>
    defaultFormState(selectedType && TYPES.includes(selectedType) ? selectedType : 'postgres'),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const activeType = selectedType

  const title = useMemo(() => {
    if (!activeType) return CREATE_DATA_SOURCE_TITLE
    return `Configure ${connectorTypeLabel(activeType)}`
  }, [activeType])

  function pickType(type: ConnectorType) {
    setSelectedType(type)
    setForm(defaultFormState(type))
  }

  async function handleSave(andTest: boolean) {
    if (!activeType) return
    setSaving(true)
    setError('')
    try {
      const key = form.key.trim() || slugConnectorKey(form.name)
      const body = {
        name: form.name.trim(),
        key,
        connector_type: activeType,
        description: form.description.trim() || null,
        config: buildConfig(activeType, form),
        secret_ref: form.secretRef.trim() || null,
        enabled: form.enabled,
      }
      const created = await api.createConnector(body)
      if (andTest && created.connector.enabled) {
        try {
          await api.testConnector(created.connector.id)
        } catch {
          /* test errors shown on detail */
        }
      }
      router.push(`/connectors/${created.connector.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <Link href="/connectors" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" />
        {appConfig.navigationConnectors}
      </Link>
      <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
      {!activeType ? (
        <p className="mt-2 text-sm text-slate-600">{CREATE_DATA_SOURCE_TYPE_HINT}</p>
      ) : null}

      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      ) : null}

      {!activeType ? (
        <div className="mt-8">
          <p className="text-sm font-semibold text-slate-800">{DATA_SOURCE_TYPE_LABEL}</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {TYPES.map(type => (
            <button
              key={type}
              type="button"
              onClick={() => pickType(type)}
              className="rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-[#FF5500] hover:shadow-sm"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-slate-100 bg-slate-50">
                <ConnectorTypeIcon connectorType={type} size={type === 'impala' ? 40 : 32} />
              </div>
              <div className="mt-3 font-semibold text-slate-900">{connectorTypeLabel(type)}</div>
              <p className="mt-2 text-xs text-slate-600">{CONNECTOR_TYPE_BLURBS[type]}</p>
            </button>
          ))}
          </div>
        </div>
      ) : (
        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
          <ConnectorTypeForm type={activeType} form={form} setForm={setForm} />
          <div className="mt-6 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={saving || !form.name.trim() || !form.host.trim()}
              onClick={() => handleSave(false)}
              className="rounded-xl bg-[#FF5500] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : SAVE_DATA_SOURCE}
            </button>
            <button
              type="button"
              disabled={saving || !form.name.trim() || !form.host.trim()}
              onClick={() => handleSave(true)}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-50"
            >
              Save & test
            </button>
            <button
              type="button"
              className="rounded-xl px-4 py-2 text-sm text-slate-600"
              onClick={() => setSelectedType(null)}
            >
              Change type
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
