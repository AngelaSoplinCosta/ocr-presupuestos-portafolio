import type { ExportColumn, Job, LocalExport, LocalReview, LocalReviewDecision, LocalReviewTable } from '../types'

const LOCAL_PILOT_HEADER = 'X-Local-Pilot'
export const LOCAL_ERROR_FALLBACK = 'No pudimos completar la operación. Inténtalo nuevamente.'
const requestsByFile = new WeakMap<File, Map<string, Promise<Job>>>()
const statusRequests = new Map<string, Promise<Job>>()
const reviewRequests = new Map<string, Promise<LocalReview>>()

const safeErrorMessages: Record<string, string> = {
  PROCESSING_CAPACITY_BUSY: 'Hay otro documento procesándose. Espera a que termine antes de intentarlo nuevamente',
  JOB_NOT_FOUND: 'No se encontró el resultado solicitado',
  RESULT_NOT_FOUND: 'El archivo ya no está disponible',
  RESULT_EXPIRED: 'El archivo ha expirado y ya no está disponible',
  RESULT_NOT_READY: 'El archivo todavía no está disponible',
  NETWORK_ERROR: 'No se pudo conectar con la API local',
  INTERNAL_ERROR: 'No se pudo completar la solicitud',
  LOCAL_MODE_DISABLED: 'La API local no está habilitada',
  LOCAL_ONLY: 'La API local sólo está disponible desde este equipo',
  LOCAL_HEADER_REQUIRED: 'No se pudo validar la solicitud local',
  CONTENT_LENGTH_REQUIRED: 'La solicitud no incluye un tamaño válido',
  CONTENT_LENGTH_INVALID: 'La solicitud no incluye un tamaño válido',
  PAYLOAD_TOO_LARGE: 'El archivo supera el tamaño permitido',
  REQUEST_TOO_LARGE: 'La solicitud supera el tamaño permitido',
  INVALID_DOCUMENT_TYPE: 'El tipo de documento no es compatible',
  INVALID_PDF: 'El archivo no es un PDF válido',
  FILE_TOO_LARGE: 'El archivo supera el tamaño permitido',
  UNSUPPORTED_DOCUMENT_TYPE: 'El tipo de documento no es compatible',
  PROCESS_INTERRUPTED: 'El procesamiento se interrumpió. Inténtalo nuevamente.',
  AUTHENTICATION_FAILED: 'No se pudo validar la solicitud',
  API_TOKEN_HASHES_INVALID: 'No se pudo validar la configuración de acceso',
  DATABASE_NOT_READY: 'La API local todavía no está lista',
  DATABASE_SCHEMA_NOT_READY: 'La API local todavía no está lista',
  DATABASE_URL_INVALID: 'La API local no está configurada correctamente',
  JOB_STORAGE_CONFIGURATION_INVALID: 'La API local no está configurada correctamente',
  JOB_STORAGE_NOT_READY: 'El almacenamiento local todavía no está listo',
  JOB_STORAGE_ROOT_INVALID: 'La API local no está configurada correctamente',
  MOTOR_ADAPTER_NOT_READY: 'El motor local todavía no está listo',
  MOTOR_CONTRACT_UNAVAILABLE: 'El motor local no está disponible',
  ACTIVE_REQUEST_LIMIT_INVALID: 'La API local no está configurada correctamente',
  REQUEST_LIMIT_INVALID: 'La API local no está configurada correctamente',
  UPLOAD_LIMIT_INVALID: 'La API local no está configurada correctamente',
  TOKEN_HEADER_LIMIT_INVALID: 'La API local no está configurada correctamente',
  INVALID_FILENAME: 'El nombre del archivo no es válido',
  INVALID_EXTENSION: 'El archivo debe tener una extensión válida',
  INVALID_MIME_TYPE: 'El tipo de archivo no es compatible',
  INVALID_ORIGINAL_NAME: 'El nombre del archivo no es válido',
  INVALID_CONTENT_SHA256: 'No se pudo validar el archivo',
  INVALID_DRIVE_REVISION: 'La versión del archivo no es válida',
  INVALID_TENANT_ID: 'No se pudo validar la solicitud',
  INVALID_STATE_TRANSITION: 'El estado del trabajo cambió. Inténtalo nuevamente.',
  STALE_JOB_TRANSITION: 'El estado del trabajo cambió. Inténtalo nuevamente.',
  UNSAFE_JOB_PATH: 'No se pudo completar la solicitud',
  UPLOAD_CLEANUP_FAILED: 'No se pudo completar la solicitud',
  INTERRUPTED_JOB_CLEANUP_FAILED: 'No se pudo completar la solicitud',
  STORAGE_PROCESSING_FAILED: 'No se pudo completar el procesamiento',
  RESULT_CLEANUP_ERROR: 'No se pudo completar la limpieza del resultado',
  RESULT_REMOVED: 'El resultado ya no está disponible',
  PERSISTENCE_ERROR: 'No se pudo completar la solicitud',
  STORAGE_ERROR: 'No se pudo completar la solicitud',
}

export class LocalJobError extends Error {
  readonly code: string

  constructor(code: string) {
    super(safeErrorMessages[code] ?? LOCAL_ERROR_FALLBACK)
    this.name = 'LocalJobError'
    this.code = code
  }
}

async function localRequest(path: string): Promise<Response> {
  try {
    return await fetch(path, { headers: { [LOCAL_PILOT_HEADER]: '1' } })
  } catch {
    throw new LocalJobError('NETWORK_ERROR')
  }
}

async function errorFromResponse(response: Response): Promise<LocalJobError> {
  const payload = await response.json().catch(() => null) as { error_code?: string } | null
  const code = typeof payload?.error_code === 'string' ? payload.error_code : 'INTERNAL_ERROR'
  return new LocalJobError(code)
}

export function createLocalJob(file: File, documentType = 'budget'): Promise<Job> {
  let requestsByType = requestsByFile.get(file)
  if (!requestsByType) {
    requestsByType = new Map()
    requestsByFile.set(file, requestsByType)
  }

  const existingRequest = requestsByType.get(documentType)
  if (existingRequest) return existingRequest

  const request = (async () => {
    const body = new FormData()
    body.append('file', file)
    body.append('document_type', documentType)

    let response: Response
    try {
      response = await fetch('/api/v1/local/jobs', {
        method: 'POST',
        headers: { [LOCAL_PILOT_HEADER]: '1' },
        body,
      })
    } catch {
      throw new LocalJobError('NETWORK_ERROR')
    }
    const payload = await response.json().catch(() => null) as Partial<Job> | { error_code?: string } | null

    if (!response.ok) {
      const errorCode = typeof payload?.error_code === 'string'
        ? payload.error_code
        : 'INTERNAL_ERROR'
      throw new LocalJobError(errorCode)
    }
    return payload as Job
  })()

  requestsByType.set(documentType, request)
  void request.catch(() => {
    if (requestsByType?.get(documentType) === request) {
      requestsByType.delete(documentType)
    }
  })
  return request
}

export function getLocalJob(jobId: string): Promise<Job> {
  const existingRequest = statusRequests.get(jobId)
  if (existingRequest) return existingRequest
  const request = (async () => {
    const response = await localRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}`)
    if (!response.ok) throw await errorFromResponse(response)
    return await response.json() as Job
  })()
  statusRequests.set(jobId, request)
  void request.finally(() => {
    if (statusRequests.get(jobId) === request) statusRequests.delete(jobId)
  }).catch(() => undefined)
  return request
}

export function getLocalJobReview(jobId: string, offset = 0, limit = 25): Promise<LocalReview> {
  const key = `${jobId}:${offset}:${limit}`
  const existingRequest = reviewRequests.get(key)
  if (existingRequest) return existingRequest
  const request = (async () => {
    const response = await localRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/review?offset=${offset}&limit=${limit}`)
    if (!response.ok) throw await errorFromResponse(response)
    return await response.json() as LocalReview
  })()
  reviewRequests.set(key, request)
  void request.finally(() => {
    if (reviewRequests.get(key) === request) reviewRequests.delete(key)
  }).catch(() => undefined)
  return request
}
export async function getLocalReviewTable(jobId: string, offset = 0, filter = 'pending'): Promise<LocalReviewTable> {
  const response = await localRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/review/table?offset=${offset}&limit=25&filter=${filter}`)
  if (!response.ok) throw await errorFromResponse(response)
  return await response.json() as LocalReviewTable
}

async function jsonRequest(path: string, method: string, body?: unknown) {
  const response = await fetch(path, { method, headers: { [LOCAL_PILOT_HEADER]: '1', ...(body ? { 'Content-Type': 'application/json' } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
  if (!response.ok) throw await errorFromResponse(response)
  return await response.json()
}
export const saveLocalDecisions = (jobId: string, review_revision: number, decisions: LocalReviewDecision[]) => jsonRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/review/decisions`, 'PUT', { review_revision, decisions })
export const getLocalExport = (jobId: string) => localRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/export`).then(async response => { if (!response.ok) throw await errorFromResponse(response); return await response.json() as LocalExport })
export const saveLocalExportConfig = (jobId: string, export_revision: number, columns: ExportColumn[]) => jsonRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/export/config`, 'PUT', { export_revision, columns }) as Promise<LocalExport>
export const generateLocalExport = (jobId: string) => jsonRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/export`, 'POST')
export async function downloadLocalSimpleExport(jobId: string): Promise<Blob> { const response = await localRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/export/result`); if (!response.ok) throw await errorFromResponse(response); return response.blob() }

export async function downloadLocalJobResult(jobId: string): Promise<Blob> {
  const response = await localRequest(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/result`)
  if (!response.ok) throw await errorFromResponse(response)
  return await response.blob()
}
