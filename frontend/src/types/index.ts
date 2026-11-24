export type DocumentType = 'Presupuesto de obra'

export type JobStatus = 'RECIBIDO' | 'PROCESANDO' | 'COMPLETADO' | 'REVISAR' | 'ERROR'

export const jobStatusLabels: Record<JobStatus, string> = {
  RECIBIDO: 'Recibido',
  PROCESANDO: 'Procesando',
  COMPLETADO: 'Listo',
  REVISAR: 'Necesita revisión',
  ERROR: 'No se pudo procesar',
}

export type JobErrorCode =
  | 'INVALID_PDF'
  | 'FILE_TOO_LARGE'
  | 'UNSUPPORTED_DOCUMENT_TYPE'
  | 'PROCESSING_CAPACITY_BUSY'
  | 'PROCESS_INTERRUPTED'
  | 'RESULT_EXPIRED'
  | 'INTERNAL_ERROR'

export interface Job {
  job_id: string
  document_type: 'budget'
  original_filename: string
  status: JobStatus
  error_code: JobErrorCode | null
  requires_review: boolean
  result_available: boolean
  result_expires_at: string | null
  created_at: string
  updated_at: string
}

export interface ReviewObservation {
  id: string
  state: string
  kind: string
  page: number | null
  row: { order: number | null; type: string; label: string }
  field: string
  extracted_value: string
  suggestion: { value: string; confidence: string } | null
  reason: string
  evidence: string[]
  allowed_actions: string[]
  requires_decision: boolean
  target?: { scope: 'cell' | 'row'; column_key?: string }
  decision?: { action: string; value: string } | null
  resolved_value?: string | null
}

export type StructuredFieldKey = 'item' | 'description' | 'unit' | 'quantity' | 'unit_price' | 'amount'
export type LocalReviewDecisionAction = 'accept_suggestion' | 'keep_original' | 'keep_provisional' | 'set_value' | 'confirm_provisional_row'
export interface LocalReviewDecision { observation_id: string; action: LocalReviewDecisionAction; field?: StructuredFieldKey; value?: string }
export interface StructuredReviewField {
  key: StructuredFieldKey
  label: string
  ocr_value: string | null
  provisional_value: string
  suggestion: { value: string; confidence: string } | null
  differs_from_ocr: boolean | null
  state: 'PENDING' | 'RESOLVED'
  decision: { action: string; value: string } | null
  can_confirm_provisional: boolean
  manual_only: boolean
}
export interface StructuredReview {
  observation_id: string
  raw_ocr_line: string
  fields: StructuredReviewField[]
  confirmed_field_count: number
  pending_field_count: number
  legacy_row_decision: { action: string; value: string } | null
}

export interface LocalReview {
  schema_version: string
  job_id: string
  status: 'REVISAR'
  review_revision: number
  total_count: number
  requires_decision_count: number
  pending_decision_count: number
  offset: number
  limit: number
  result_expires_at: string
  observations: ReviewObservation[]
}

export interface ExportColumn { key: string; label: string; data_type: 'text' | 'decimal' | 'currency'; source_header?: string | null; included: boolean; position: number; origin: 'standard' | 'candidate' }
export interface LocalExport { export_revision: number; source_review_revision: number; columns: ExportColumn[]; pending_decision_count: number; simple_result_available: boolean }
export interface LocalReviewRow { row_key: string; page: number | null; order: number | null; cells: Record<string, string>; observations: ReviewObservation[]; structured_review?: StructuredReview | null }
export interface LocalReviewTable { review_revision: number; pending_decision_count: number; filter: 'pending' | 'resolved' | 'all'; offset: number; limit: number; total_count: number; columns: ExportColumn[]; rows: LocalReviewRow[] }

export type DocumentStatus =
  | 'Recibido'
  | 'Procesando'
  | 'Listo'
  | 'Necesita revisión'
  | 'No se pudo procesar'

export interface ColumnDefinition {
  key: string
  defaultLabel: string
  label: string
  included: boolean
  detail: string
  origin: 'detected' | 'fixed' | 'blank'
  position: number
  userCreated: boolean
  fixedValue?: string
  linkedField?: string
}

export interface DetectedField {
  key: string
  label: string
  sample: string
  detail: string
}

export interface Observation {
  id: string
  field: string
  page: number
  context: string
  detected: string
  suggested: string
  reason: string
  confidence: 'Media' | 'Baja'
  evidence: string
  linkedField?: string
  critical: boolean
}

export type DecisionKind = 'suggested' | 'detected' | 'manual'

export interface Decision {
  kind: DecisionKind
  value: string
}

export interface DemoDocument {
  id: string
  name: string
  type: DocumentType
  date: string
  records: number | null
  status: DocumentStatus
}
