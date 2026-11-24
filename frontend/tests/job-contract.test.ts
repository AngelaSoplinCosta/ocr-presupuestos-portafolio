import { describe, expect, it } from 'vitest'
import { jobStatusLabels, type DocumentType, type Job, type JobErrorCode, type JobStatus } from '../src/types'

describe('contrato compartido del trabajo', () => {
  it('mantiene estados y textos visibles', () => {
    const statuses: JobStatus[] = ['RECIBIDO', 'PROCESANDO', 'COMPLETADO', 'REVISAR', 'ERROR']
    expect(statuses.map((status) => jobStatusLabels[status])).toEqual([
      'Recibido',
      'Procesando',
      'Listo',
      'Necesita revisión',
      'No se pudo procesar',
    ])
  })

  it('mantiene el tipo documental y los códigos de error del MVP', () => {
    const documentType: DocumentType = 'Presupuesto de obra'
    const errorCodes: JobErrorCode[] = [
      'INVALID_PDF',
      'FILE_TOO_LARGE',
      'UNSUPPORTED_DOCUMENT_TYPE',
      'PROCESSING_CAPACITY_BUSY',
      'PROCESS_INTERRUPTED',
      'RESULT_EXPIRED',
      'INTERNAL_ERROR',
    ]
    const job: Job = {
      job_id: 'job-1',
      document_type: 'budget',
      original_filename: 'presupuesto.pdf',
      status: 'RECIBIDO',
      error_code: null,
      requires_review: false,
      result_available: false,
      result_expires_at: null,
      created_at: '2026-08-20T00:00:00Z',
      updated_at: '2026-08-20T00:00:00Z',
    }

    expect(documentType).toBe('Presupuesto de obra')
    expect(errorCodes).toHaveLength(7)
    expect(job.document_type).toBe('budget')
  })
})
