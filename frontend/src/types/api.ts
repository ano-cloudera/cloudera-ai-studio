export type ProviderName = 'qwen' | 'gemini' | 'openai'

export type DocumentStatus = 'UPLOADED' | 'QUEUED' | 'PROCESSING' | 'READY' | 'FAILED'

export type SkillRecord = {
  id: string
  workspace_id: string
  project_id: string | null
  name: string
  key: string
  scope: 'workspace' | 'project'
  description: string | null
  status: string
  active_version_id: string | null
  created_at: string
  updated_at: string
}

export type SkillVersionRecord = {
  id: string
  skill_id: string
  version_number: number
  instructions: string
  prompt_key: string | null
  input_schema: Record<string, unknown> | null
  output_schema: Record<string, unknown> | null
  allowed_tools: string[]
  config: Record<string, unknown>
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED'
  created_at: string
}

export type SkillToolRecord = {
  key: string
  name: string
  description: string
  enabled: boolean
  input_schema?: Record<string, unknown> | null
}

export type SkillExecuteResult = {
  status: string
  result: Record<string, unknown>
  execution: {
    skill_id: string
    skill_key: string
    skill_version: number
    skill_version_id: string
    handler_type: string
    tools_used: string[]
    prompt_key?: string | null
    prompt_source?: string | null
    execution_ms: number
    connector_type?: string | null
    connector_name?: string | null
  }
}

export type PromptRecord = {
  id: string
  workspace_id: string | null
  project_id: string | null
  name: string
  key: string
  scope: 'global' | 'workspace' | 'project'
  description: string | null
  active_version_id: string | null
  created_at: string
  updated_at: string
}

export type PromptVersionRecord = {
  id: string
  prompt_id: string
  version_number: number
  content: string
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED'
  created_by: string | null
  created_at: string
}

export type SemanticModelRecord = {
  id: string
  workspace_id: string
  project_id: string
  name: string
  key: string
  description: string | null
  active_version_id: string | null
  created_at: string
  updated_at: string
}

export type SemanticVersionRecord = {
  id: string
  semantic_model_id: string
  version_number: number
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED'
  created_by: string | null
  created_at: string
  updated_at: string
  published_at: string | null
  runtime_adapter: string | null
  runtime_artifact_uri: string | null
  runtime_artifact_checksum: string | null
  runtime_artifact_version: string | null
  activation_readiness?: string | null
}

export type SemanticRuntimeDeploymentRecord = {
  id: string
  semantic_model_id: string
  semantic_version_id: string
  registry_version_number: number
  status: string
  artifact_uri: string
  artifact_checksum: string
  runtime_adapter: string
  health_status: string | null
  error_summary: string | null
  created_at: string
  activated_at: string | null
  created_by: string | null
}

export type SemanticRuntimeStatus = {
  semantic_model_key?: string
  registry_active_version: number | null
  runtime_active_version: number | null
  runtime_status: string
  loader_mode: string
  deployment: {
    deployment_id: string
    artifact_checksum: string
    activated_at: string | null
    adapter: string
    health: string | null
  } | null
}

export type SemanticRecentDefinitionRecord = {
  object_id: string
  object_kind: string
  name: string
  type: string
  definition: string
  source: string
  status: string
  modified_at: string | null
}

export type SemanticEntityRecord = {
  id: string
  key: string
  name: string
  modified_at?: string | null
  description: string | null
  source_type: string
  catalog: string | null
  schema: string | null
  table_name: string | null
  view_name: string | null
  primary_key: string | null
  connection_id: string | null
  metadata: Record<string, unknown>
}

export type SemanticEntityImportPreview = {
  table_type: string
  columns: {
    name: string
    native_type: string
    normalized_type: string
    nullable: boolean | null
    comment: string | null
  }[]
  candidate_dimensions: { column: string; suggested_key: string; normalized_type: string }[]
  existing_entity: { id: string; key: string; name: string } | null
  primary_key: string[] | null
}

export type SemanticEntityImportResult = {
  entity: SemanticEntityRecord
  import: {
    dimensions_created: number
    columns_discovered: number
    warnings: string[]
  }
}

export type ConnectorReferences = {
  count: number
  entities: {
    entity_id: string
    entity_key: string
    entity_name: string
    semantic_model_key: string
    semantic_model_name: string
  }[]
}

export type SemanticMetricRecord = {
  id: string
  key: string
  name: string
  modified_at?: string | null
  description: string | null
  business_definition: string | null
  expression: string
  aggregation: string | null
  source_entity_key: string
  format: string | null
  unit: string | null
  synonyms: string[]
  /** Empty = publish uses all dimensions on the metric data model (and related models). */
  allowed_dimension_keys: string[]
  metadata: Record<string, unknown>
}

export type SemanticDimensionRecord = {
  id: string
  key: string
  name: string
  modified_at?: string | null
  description: string | null
  source_entity_key: string
  source_column: string
  data_type: string | null
  synonyms: string[]
  metadata: Record<string, unknown>
}

export type SemanticRelationshipRecord = {
  id: string
  key: string
  name: string
  modified_at?: string | null
  from_entity_key: string
  to_entity_key: string
  relationship_type: string
  join_type: string
  join_expression: string
  description: string | null
  metadata: Record<string, unknown>
}

export type SemanticTermRecord = {
  id: string
  key: string
  term: string
  modified_at?: string | null
  definition: string | null
  synonyms: string[]
  related_metric_keys: string[]
  related_dimension_keys: string[]
  related_entity_keys: string[]
  metadata: Record<string, unknown>
}

export type SemanticValidationIssue = {
  id?: string | null
  code: string
  message: string
  severity: 'ERROR' | 'WARNING' | 'INFO'
  category?: string
  object_type?: string | null
  object_key?: string | null
  remediation?: string | null
  metadata?: Record<string, unknown>
  path?: string | null
}

export type SemanticValidationSummary = {
  valid: boolean
  activation_ready: boolean
  readiness: 'NOT_READY' | 'READY_WITH_WARNINGS' | 'READY'
  readiness_score: number
  error_count: number
  warning_count: number
  info_count: number
  checks_run: number
  checks_skipped: number
  duration_ms: number
  stages: string[]
}

export type SemanticValidationResult = {
  valid: boolean
  errors: SemanticValidationIssue[]
  warnings: SemanticValidationIssue[]
  info?: SemanticValidationIssue[]
  summary?: SemanticValidationSummary
  readiness?: SemanticValidationSummary['readiness']
  activation_ready?: boolean
  readiness_score?: number
  run_id?: string | null
  issues_by_category?: Record<string, SemanticValidationIssue[]>
  connection_status?: Record<string, string>
}

export type SemanticValidationRunRecord = {
  id: string
  semantic_version_id: string
  started_at: string
  completed_at: string | null
  status: string
  mode: string
  summary: SemanticValidationSummary | Record<string, unknown>
  validator_version: string
}

export type SemanticVersionDiff = {
  left_version_id: string
  right_version_id: string
  left_version_number: number
  right_version_number: number
  sections: Array<{
    section: string
    added: string[]
    removed: string[]
    changed: Array<Record<string, unknown>>
  }>
  breaking_changes: Array<Record<string, unknown>>
}

export type ValidatorHealth = {
  impala: { status: string; label: string }
  trino: { status: string; label: string }
}

export type SemanticArtifactPreview = {
  adapter: string
  version: string
  uri: string | null
  checksum: string
  content_preview: string
  metadata: Record<string, unknown>
}

export type OssieImportSummary = {
  imported: {
    entities: number
    metrics: number
    dimensions: number
    relationships: number
    terms: number
  }
  warnings: string[]
  errors: string[]
  semantic_model_id: string | null
  semantic_version_id: string | null
  validation: SemanticValidationResult | null
}

export type OssieImportSource = {
  project_dir: string
  ossie_file: string
  exists: boolean
}

export type PromptResolveResult = {
  prompt_key: string
  source: string
  source_label: string
  chain: string[]
  layers?: Array<{
    scope: string
    prompt_id: string
    version_number: number
    status: string
  }>
  content: string
  file_fallback_preview?: string
}

export type LibraryLifecycleStatus = 'ready' | 'processing' | 'attention'

export type LibraryRecord = {
  id: string
  workspace_id: string
  project_id: string
  name: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
  document_count?: number
  library_status?: LibraryLifecycleStatus | string
  document_limit?: number
}

export type PaginatedResult<T> = {
  items: T[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export type BulkDeleteResultItem = { id: string; name: string }
export type BulkDeleteFailedItem = BulkDeleteResultItem & { code: string; message: string }

export type BulkDeleteResponse = {
  requested: number
  deleted: BulkDeleteResultItem[]
  failed: BulkDeleteFailedItem[]
  deleted_count: number
  failed_count: number
}

export type ChatContextSourcePayload = {
  type:
    | 'knowledge_library'
    | 'uploaded_file'
    | 'table'
    | 'semantic_model'
    | 'semantic_entity'
    | 'semantic_metric'
    | 'semantic_term'
    | 'mcp_connector'
  id: string
  name: string
  metadata?: Record<string, unknown>
}

export type ChatContextOptionGroup = {
  id: string
  label: string
  options: Array<{
    type: ChatContextSourcePayload['type']
    id: string
    name: string
    subtitle?: string
    group?: string
    metadata?: Record<string, unknown>
  }>
}

export type DocumentRecord = {
  id: string
  workspace_id: string
  project_id: string
  library_id: string
  filename: string
  original_filename: string
  mime_type: string
  size_bytes: number
  status: DocumentStatus
  checksum: string | null
  metadata?: Record<string, unknown> | null
  processing_stage?: string | null
  error_summary?: string | null
  chunk_count?: number | null
  created_at: string
  updated_at: string
}

export type ModelInfo = {
  provider: ProviderName
  id: string
  label: string
  available: boolean
  reason: string | null
}

export type ModelSelection = { provider: ProviderName; model: string }

export type ChatMode = 'ask_data' | 'rag'

export type GroundingLevel = 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'INSUFFICIENT_EVIDENCE'

export type CitationRecord = {
  document_id: string
  filename?: string | null
  page_number?: number | null
  section?: string | null
  chunk_id: string
  source_uri?: string | null
  snippet: string
  score: number
}

export type ChartSpec = {
  type: 'bar' | 'line' | 'area' | 'scatter' | 'pie' | 'table' | 'kpi'
  title: string
  x?: string | null
  y?: string | null
  series?: string | null
}

export type AnalysisOutput = {
  direct_answer: string
  executive_summary: string
  insights: string[]
  business_implications: string[]
  caveats: string[]
  data_reference: string
  chart_spec: ChartSpec | null
}

export type AskDataClarificationOption = {
  type: string
  id: string
  name: string
}

export type AskDataClarification = {
  reason: string
  message: string
  options: AskDataClarificationOption[]
}

export type ChatResponse = {
  request_id: string
  session_id: string
  status: 'SUCCESS' | 'CLARIFICATION' | 'clarification_required' | 'NO_DATA' | 'UNSUPPORTED' | 'ERROR'
  provider: ProviderName
  model: string
  strategy:
    | 'governed'
    | 'sql_fallback'
    | 'clarification'
    | 'unsupported'
    | 'conversational'
    | 'exploratory_local'
    | 'local_agent_exploratory'
    | 'error'
    | 'rag'
  route?: 'ask_data' | 'rag' | null
  grounding?: GroundingLevel | null
  citations?: CitationRecord[] | null
  retrieval?: { candidate_count: number; selected_count: number } | null
  answer: AnalysisOutput
  data: {
    columns: string[]
    rows: Record<string, unknown>[]
    row_count: number
    execution_ms: number
    connector_type?: string | null
    connector_name?: string | null
    governed_metric?: string | null
    governed_metric_display_name?: string | null
    governed_metric_expression?: string | null
    governed_base_dataset?: string | null
    unit_format?: string | null
  }
  chart_spec: ChartSpec | null
  timings: {
    context_ms?: number
    planning_ms?: number
    validation_ms?: number
    agent_ms?: number
    query_ms?: number
    analysis_ms?: number
    total_ms: number
  }
  retry_count: number
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    llm_calls: number
  } | null
  governed_sql?: string | null
  context_mode?: 'RAW_TABLE' | 'GOVERNED_SEMANTIC' | null
  clarification?: AskDataClarification | null
  presentation_tier?: 1 | 2 | 3 | null
}

export type SemanticOverviewPayload = {
  model: { id: string; name: string; key: string; updated_at: string | null }
  state: string
  readiness: string
  issue_count: number
  published_version_number: number | null
  draft_version_number: number | null
  counts: {
    entities: number
    metrics: number
    dimensions: number
    relationships: number
    terms: number
  }
  ready_to_publish: boolean
}

export type UsageTotals = {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  llm_calls: number
  turns: number
}

export type UsageSummary = {
  period_days: number | null
  mtd: boolean
  totals: UsageTotals
  mtd_totals: UsageTotals
  daily: { day: string; tokens: number }[]
  by_model: { provider: string; model: string; tokens: number; turns: number }[]
  monthly_token_budget: number
}

export type UsageEvent = {
  created_at: string
  request_id: string
  session_id: string
  provider: string
  model: string
  strategy: string
  status: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  llm_calls: number
}

export type SuggestedQuestion = {
  id: string
  question: string
  domain: string
  domains: string[]
  difficulty: 'simple' | 'medium' | 'complex'
  analysis_type: string
  expected_visualization: string
}

export type StarterSource = 'configured' | 'question_bank' | 'semantic_runtime'

export type PresentationTierOverridesPayload = {
  enabled?: boolean | null
  panel_auto_open?: 'heuristic' | 'always' | 'never' | null
  tier3_min_rows?: number | null
  tier3_min_insights?: number | null
  tier3_min_implications?: number | null
  rank_tier3_above_n?: number | null
  rank_min_tier?: 1 | 2 | 3 | null
  tier1_max_rows?: number | null
  tier1_max_columns?: number | null
  force_tier3_on_pareto?: boolean | null
  force_tier3_on_operational_analysis?: boolean | null
  force_tier3_on_visual_chart?: boolean | null
  chat_expand_tier1?: boolean | null
  chat_expand_tier2?: boolean | null
  chat_details_default_open?: boolean | null
  audience_mode?: 'executive' | 'analyst' | null
  tier1_show_narrative?: boolean | null
}

export type McpTransport = 'stdio' | 'sse'

export type McpServerEntryPayload = {
  id: string
  name: string
  description?: string
  enabled: boolean
  transport: McpTransport
  command?: string | null
  args: string[]
  env_var_names: string[]
  url?: string | null
  header_env_var_names: Record<string, string>
  default_tool?: string | null
}

export type McpWorkspaceSettingsPayload = {
  servers: McpServerEntryPayload[]
}

export type McpTestConnectionResult = {
  ok: boolean
  message: string
  tools: string[]
  latency_ms: number
  missing_env_var_names: string[]
}

export type AskDataSettingsPayload = {
  starter_questions_caption: string
  starter_questions: string[]
  starter_source: StarterSource
  question_bank_limit: number
  question_bank_domain: string | null
  question_bank_difficulty: 'simple' | 'medium' | 'complex' | null
  presentation?: PresentationTierOverridesPayload | null
  default_semantic_model_id?: string | null
  auto_attach_semantic_model?: boolean
  instruction_prompt_key?: string | null
}

export type AskDataSemanticCatalogResponse = {
  workspace_slug: string
  model: { id: string; name: string; key: string } | null
  metrics: { id: string; key: string; name: string; description?: string }[]
  dimensions: { id: string; key: string; name: string; description?: string }[]
}

export type AskDataStartersResponse = {
  caption: string
  source: StarterSource
  questions: SuggestedQuestion[]
}

export type ConnectorType = 'impala' | 'trino' | 'postgres'

export type ConnectorRecord = {
  id: string
  workspace_id: string
  project_id: string | null
  name: string
  key: string
  description: string | null
  connector_type: ConnectorType
  status: string
  enabled: boolean
  config: Record<string, unknown>
  secret_ref: string | null
  credentials_configured: boolean
  last_tested_at: string | null
  last_test_status: string | null
  last_test_message: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  created_by: string | null
}

export type ConnectorCreateRequest = {
  name: string
  key: string
  connector_type: ConnectorType
  config: Record<string, unknown>
  description?: string | null
  secret_ref?: string | null
  enabled?: boolean
  metadata?: Record<string, unknown> | null
}

export type ConnectorUpdateRequest = {
  name?: string
  description?: string | null
  config?: Record<string, unknown>
  secret_ref?: string | null
  enabled?: boolean
  metadata?: Record<string, unknown> | null
}

export type ConnectorCapabilities = {
  sql: boolean
  metadata: boolean
  catalogs: boolean
  schemas: boolean
  tables: boolean
  views: boolean
  read_only_query: boolean
  sample_preview: boolean
  transactions: boolean
  kerberos: boolean
}

export type ConnectorTestResult = {
  status: string
  latency_ms: number
  server_version: string | null
  server_name: string | null
  default_catalog: string | null
  default_schema: string | null
  message: string
  error_code: string | null
  phases: Record<string, string> | null
  capabilities: ConnectorCapabilities
}

export type CatalogInfo = { name: string; comment: string | null }
export type SchemaInfo = { name: string; catalog: string | null; comment: string | null }
export type TableInfo = {
  name: string
  schema: string | null
  catalog: string | null
  table_type: string
  comment: string | null
}

export type ColumnInfo = {
  name: string
  data_type: string
  native_type: string
  normalized_type: string
  nullable: boolean | null
  ordinal_position: number | null
  comment: string | null
}

export type TableDetail = {
  catalog: string | null
  schema: string | null
  name: string
  table_type: string
  comment: string | null
  primary_key: string[] | null
  metadata: Record<string, unknown>
  columns: ColumnInfo[]
}

export type SamplePreview = {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  truncated: boolean
  query_duration_ms: number
  resolved_context: {
    catalog: string | null
    schema: string | null
    table: string | null
  }
}

export type AiProviderType = 'OPENAI' | 'GEMINI' | 'ANTHROPIC' | 'OPENAI_COMPATIBLE'
export type AiRemoteModel = { id: string; display_name?: string | null }
export type AiModelType = 'CHAT' | 'EMBEDDING' | 'RERANKER'
export type AssignmentCapability =
  | 'CHAT_DEFAULT'
  | 'ASK_DATA'
  | 'RAG_GENERATION'
  | 'SKILLS'
  | 'EMBEDDING'
  | 'RERANKER'
export type AssignmentSource = 'PROJECT' | 'WORKSPACE' | 'LEGACY_FALLBACK'

export type AiProviderRecord = {
  id: string
  name: string
  key: string
  provider_type: AiProviderType
  base_url: string | null
  secret_ref: string | null
  secret_configured: boolean
  enabled: boolean
  status: string
  config_json: Record<string, unknown>
  last_test_at: string | null
  created_at: string
  updated_at: string
}

export type AiModelRecord = {
  id: string
  provider_id: string
  name: string
  key: string
  model_id: string
  model_type: AiModelType
  enabled: boolean
  capabilities: {
    streaming: boolean | null
    tools: boolean | null
    json_mode: boolean | null
    vision: boolean | null
  }
  context_window: number | null
  max_output_tokens: number | null
  provider_type: string | null
  status: string
  config_json: Record<string, unknown>
  last_test_at: string | null
}

export type ModelAssignmentRecord = {
  capability: AssignmentCapability
  model_id: string | null
  model_name: string | null
  model_key: string | null
  provider_type: string | null
  enabled: boolean
  source: AssignmentSource
  health?: string | null
}

export type AiProviderTestResult = {
  status: string
  latency_ms: number
  provider_type?: string
  error_code?: string | null
  message?: string | null
}

export type AiModelTestResult = {
  status: string
  latency_ms: number
  model_type?: string
  error_code?: string | null
  message?: string | null
}
