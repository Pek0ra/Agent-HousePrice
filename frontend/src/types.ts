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
  details: ExecutionDetails
}

export interface Conversation {
  id: string
  question: string
  createdAt: string
  response?: ChatResponse
  error?: string
}
