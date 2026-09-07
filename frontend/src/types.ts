export type CellValue = string | number | boolean | null

export interface RetrievedMetric {
  id: string
  title: string
  description: string
}

export interface ExecutionDetails {
  data_source: 'mysql' | 'hive' | 'none' | string
  duration_ms: number
  selected_tables: string[]
  retrieved_metrics: RetrievedMetric[]
  row_count: number
  retry_count: number
  used_history: boolean
  inherited_fields: string[]
  overridden_fields: string[]
  context_resolution_duration_ms: number
  model_calls?: number
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
}

export interface ChartConfig {
  type: 'bar' | 'line' | 'pie'
  title: string
  x_field: string
  y_fields: string[]
}

export interface ChatResponse {
  answer: string
  sql: string | null
  columns: string[]
  rows: CellValue[][]
  chart: ChartConfig | null
  trace_id: string
  thread_id: string
  details: ExecutionDetails
}

export interface Conversation {
  id: string
  threadId: string | null
  title: string
  createdAt: string
  updatedAt: string
  turns: ChatTurn[]
}

export interface ChatTurn {
  id: string
  question: string
  createdAt: string
  response?: ChatResponse
  error?: string
}
