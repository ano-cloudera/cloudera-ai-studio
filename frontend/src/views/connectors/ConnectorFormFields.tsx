'use client'

import type { Dispatch, ReactNode, SetStateAction } from 'react'
import type { ConnectorType } from '../../types/api'
import { DATA_SOURCE_NAME_LABEL } from './dataSourceUx'

export type ConnectorFormState = {
  name: string
  key: string
  description: string
  secretRef: string
  enabled: boolean
  host: string
  port: string
  database: string
  catalog: string
  schema: string
  httpScheme: 'http' | 'https'
  authType: string
  username: string
  ssl: boolean
  httpTransport: boolean
  verifySsl: boolean
  sslmode: string
  kerberosServiceName: string
  timeoutSeconds: string
}

export function defaultFormState(type: ConnectorType): ConnectorFormState {
  if (type === 'impala') {
    return {
      name: '',
      key: '',
      description: '',
      secretRef: '',
      enabled: true,
      host: '',
      port: '21050',
      database: 'default',
      catalog: '',
      schema: '',
      httpScheme: 'http',
      authType: 'plain',
      username: '',
      ssl: false,
      httpTransport: false,
      verifySsl: true,
      sslmode: 'prefer',
      kerberosServiceName: 'impala',
      timeoutSeconds: '',
    }
  }
  if (type === 'trino') {
    return {
      name: '',
      key: '',
      description: '',
      secretRef: '',
      enabled: true,
      host: '',
      port: '8080',
      database: '',
      catalog: '',
      schema: '',
      httpScheme: 'http',
      authType: 'none',
      username: 'trino',
      ssl: false,
      httpTransport: false,
      verifySsl: true,
      sslmode: 'prefer',
      kerberosServiceName: '',
      timeoutSeconds: '',
    }
  }
  return {
    name: '',
    key: '',
    description: '',
    secretRef: '',
    enabled: true,
    host: '',
    port: '5432',
    database: '',
    catalog: '',
    schema: '',
    httpScheme: 'http',
    authType: 'plain',
    username: '',
    ssl: false,
    httpTransport: false,
    verifySsl: true,
    sslmode: 'prefer',
    kerberosServiceName: '',
    timeoutSeconds: '',
  }
}

export function buildConfig(type: ConnectorType, form: ConnectorFormState): Record<string, unknown> {
  const timeout =
    form.timeoutSeconds.trim() === '' ? undefined : Number.parseInt(form.timeoutSeconds, 10)
  if (type === 'impala') {
    return {
      host: form.host.trim(),
      port: Number.parseInt(form.port, 10) || 21050,
      database: form.database.trim() || 'default',
      auth_type: form.authType,
      username: form.username.trim() || null,
      kerberos_service_name: form.authType === 'gssapi' ? form.kerberosServiceName.trim() || 'impala' : null,
      ssl: form.ssl,
      http_transport: form.httpTransport,
      ...(timeout != null && !Number.isNaN(timeout) ? { timeout_seconds: timeout } : {}),
    }
  }
  if (type === 'trino') {
    return {
      host: form.host.trim(),
      port: Number.parseInt(form.port, 10) || 8080,
      catalog: form.catalog.trim(),
      schema: form.schema.trim() || null,
      http_scheme: form.httpScheme,
      auth_type: form.authType,
      username: form.username.trim() || null,
      verify_ssl: form.verifySsl,
      ...(timeout != null && !Number.isNaN(timeout) ? { timeout_seconds: timeout } : {}),
    }
  }
  return {
    host: form.host.trim(),
    port: Number.parseInt(form.port, 10) || 5432,
    database: form.database.trim(),
    username: form.username.trim() || null,
    sslmode: form.sslmode,
    ...(timeout != null && !Number.isNaN(timeout) ? { timeout_seconds: timeout } : {}),
  }
}

export function formFromConnector(type: ConnectorType, config: Record<string, unknown>): Partial<ConnectorFormState> {
  return {
    host: String(config.host ?? ''),
    port: config.port != null ? String(config.port) : defaultFormState(type).port,
    database: String(config.database ?? ''),
    catalog: String(config.catalog ?? ''),
    schema: String(config.schema ?? ''),
    httpScheme: (config.http_scheme as 'http' | 'https') || 'http',
    authType: String(config.auth_type ?? 'plain'),
    username: String(config.username ?? ''),
    ssl: Boolean(config.ssl),
    httpTransport: Boolean(config.http_transport),
    verifySsl: config.verify_ssl !== false,
    sslmode: String(config.sslmode ?? 'prefer'),
    kerberosServiceName: String(config.kerberos_service_name ?? 'impala'),
    timeoutSeconds: config.timeout_seconds != null ? String(config.timeout_seconds) : '',
  }
}

type FieldProps = {
  label: string
  children: ReactNode
  hint?: string
}

export function Field({ label, children, hint }: FieldProps) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-slate-500">{hint}</span> : null}
    </label>
  )
}

function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3 border-0 p-0">
      <legend className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</legend>
      <div className="grid gap-4">{children}</div>
    </fieldset>
  )
}

const inputClass =
  'mt-0.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#FF5500] focus:ring-1 focus:ring-[#FF5500]'

export function ConnectorTypeForm({
  type,
  form,
  setForm,
  credentialsConfigured,
}: {
  type: ConnectorType
  form: ConnectorFormState
  setForm: Dispatch<SetStateAction<ConnectorFormState>>
  credentialsConfigured?: boolean
}) {
  const set = (patch: Partial<ConnectorFormState>) => setForm(prev => ({ ...prev, ...patch }))

  return (
    <div className="grid gap-8">
      <FormSection title="General">
        <Field label={DATA_SOURCE_NAME_LABEL}>
          <input className={inputClass} value={form.name} onChange={e => set({ name: e.target.value })} required />
        </Field>
        <Field label="Description">
          <textarea
            className={inputClass}
            rows={2}
            value={form.description}
            onChange={e => set({ description: e.target.value })}
          />
        </Field>
      </FormSection>

      <FormSection title="Connection">
        <Field label="Host">
          <input className={inputClass} value={form.host} onChange={e => set({ host: e.target.value })} required />
        </Field>
        <Field label="Port">
          <input className={inputClass} value={form.port} onChange={e => set({ port: e.target.value })} required />
        </Field>

      {type === 'impala' ? (
        <>
          <Field label="Database / catalog">
            <input className={inputClass} value={form.database} onChange={e => set({ database: e.target.value })} />
          </Field>
        </>
      ) : null}

      {type === 'trino' ? (
        <>
          <Field label="HTTP scheme">
            <select
              className={inputClass}
              value={form.httpScheme}
              onChange={e => set({ httpScheme: e.target.value as 'http' | 'https' })}
            >
              <option value="http">http</option>
              <option value="https">https</option>
            </select>
          </Field>
          <Field label="Default catalog">
            <input className={inputClass} value={form.catalog} onChange={e => set({ catalog: e.target.value })} />
          </Field>
          <Field label="Default schema">
            <input className={inputClass} value={form.schema} onChange={e => set({ schema: e.target.value })} />
          </Field>
        </>
      ) : null}

      {type === 'postgres' ? (
        <>
          <Field label="Database">
            <input className={inputClass} value={form.database} onChange={e => set({ database: e.target.value })} required />
          </Field>
          <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
            Datasource PostgreSQL connections are independent from the accelerator&apos;s internal platform database.
          </p>
        </>
      ) : null}
      </FormSection>

      <FormSection title="Authentication">
        {type === 'impala' ? (
          <>
            <Field label="Authentication type">
              <select className={inputClass} value={form.authType} onChange={e => set({ authType: e.target.value })}>
                <option value="none">None</option>
                <option value="plain">Username / Password</option>
                <option value="ldap">LDAP</option>
                <option value="gssapi">Kerberos</option>
              </select>
            </Field>
            {form.authType !== 'none' && form.authType !== 'gssapi' ? (
              <Field label="Username">
                <input className={inputClass} value={form.username} onChange={e => set({ username: e.target.value })} />
              </Field>
            ) : null}
            {form.authType === 'gssapi' ? (
              <Field label="Kerberos service name">
                <input
                  className={inputClass}
                  value={form.kerberosServiceName}
                  onChange={e => set({ kerberosServiceName: e.target.value })}
                />
              </Field>
            ) : null}
          </>
        ) : null}
        {type === 'trino' ? (
          <>
            <Field label="Authentication type">
              <select className={inputClass} value={form.authType} onChange={e => set({ authType: e.target.value })}>
                <option value="none">None</option>
                <option value="plain">Username / Password</option>
              </select>
            </Field>
            {form.authType === 'plain' ? (
              <Field label="Username">
                <input className={inputClass} value={form.username} onChange={e => set({ username: e.target.value })} />
              </Field>
            ) : null}
          </>
        ) : null}
        {type === 'postgres' ? (
          <Field label="Username">
            <input className={inputClass} value={form.username} onChange={e => set({ username: e.target.value })} />
          </Field>
        ) : null}
        <Field
          label="Secret reference"
          hint="Credentials are resolved by the backend. Values are never shown in the UI."
        >
          <input
            className={inputClass}
            value={form.secretRef}
            onChange={e => set({ secretRef: e.target.value })}
            placeholder="env://CONNECTOR_SECRET"
          />
        </Field>
        {credentialsConfigured ? (
          <p className="text-sm text-emerald-700">Credentials configured</p>
        ) : form.secretRef.trim() ? (
          <p className="text-sm text-slate-600">Secret reference will be saved; values are never shown after save.</p>
        ) : null}
      </FormSection>

      <FormSection title="Security">
        {type === 'impala' ? (
          <>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={form.ssl} onChange={e => set({ ssl: e.target.checked })} />
              Use SSL
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={form.httpTransport} onChange={e => set({ httpTransport: e.target.checked })} />
              HTTP transport
            </label>
          </>
        ) : null}
        {type === 'trino' ? (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={form.verifySsl} onChange={e => set({ verifySsl: e.target.checked })} />
            Verify SSL
          </label>
        ) : null}
        {type === 'postgres' ? (
          <Field label="SSL mode">
            <select className={inputClass} value={form.sslmode} onChange={e => set({ sslmode: e.target.value })}>
              <option value="disable">disable</option>
              <option value="prefer">prefer</option>
              <option value="require">require</option>
              <option value="verify-ca">verify-ca</option>
              <option value="verify-full">verify-full</option>
            </select>
          </Field>
        ) : null}
      </FormSection>

      <FormSection title="Advanced">
        <Field label="Key" hint="Unique identifier within this project. Auto-generated from name if left blank.">
          <input className={inputClass} value={form.key} onChange={e => set({ key: e.target.value })} placeholder="optional" />
        </Field>
        <Field label="Timeout (seconds)" hint="Optional query/connect timeout override.">
          <input className={inputClass} value={form.timeoutSeconds} onChange={e => set({ timeoutSeconds: e.target.value })} />
        </Field>
      </FormSection>
    </div>
  )
}
