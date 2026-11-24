import { describe, expect, it, vi } from 'vitest'
import { createLocalJob, downloadLocalJobResult, getLocalJob } from '../src/api/localJobs'
import { renderAt, renderStrictAt } from './testUtils'
import { screen } from '@testing-library/react'
import { waitFor } from '@testing-library/react'
import { jobStatusLabels } from '../src/types'
import viteConfigSource from '../vite.config.ts?raw'

describe('carga local real', () => {
  const successBody = {
    job_id: 'job-1', document_type: 'budget', original_filename: 'presupuesto.pdf',
    status: 'COMPLETADO', error_code: null, requires_review: false,
    result_available: true, result_expires_at: null,
    created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z',
  }

  it('envía sólo el marcador local y los campos del formulario', async () => {
    const responseBody = {
      job_id: 'job-1',
      document_type: 'budget',
      original_filename: 'presupuesto.pdf',
      status: 'COMPLETADO',
      error_code: null,
      requires_review: false,
      result_available: true,
      result_expires_at: '2026-08-21T00:00:00Z',
      created_at: '2026-08-20T00:00:00Z',
      updated_at: '2026-08-20T00:00:00Z',
    }
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(responseBody), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchSpy)

    await createLocalJob(new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' }))

    const [, request] = fetchSpy.mock.calls[0]
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/local/jobs', expect.objectContaining({
      method: 'POST',
      headers: { 'X-Local-Pilot': '1' },
    }))
    expect(request?.headers).not.toHaveProperty('X-API-Key')
    expect(request?.headers).not.toHaveProperty('X-Drive-File-Id')
    expect(request?.body).toBeInstanceOf(FormData)
    expect((request?.body as FormData).get('document_type')).toBe('budget')
    expect((request?.body as FormData).get('file')).toBeInstanceOf(File)
  })

  it('no reintenta automáticamente y mantiene el envío bloqueado mientras espera', async () => {
    let resolveRequest: ((value: Response) => void) | undefined
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { resolveRequest = resolve })))
    const { user } = renderAt('/documentos/nuevo')
    const input = screen.getByLabelText('Seleccionar documento PDF')
    await user.upload(input, new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a procesamiento' }))

    expect(screen.getByRole('button', { name: 'Enviando documento' })).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(1)
    resolveRequest?.(new Response(JSON.stringify({
      job_id: 'job-1', document_type: 'budget', original_filename: 'presupuesto.pdf',
      status: 'COMPLETADO', error_code: null, requires_review: false,
      result_available: true, result_expires_at: null,
      created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z',
    }), { status: 200 }))
  })

  it('deduplica el montaje de ProcessingPage bajo StrictMode', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(successBody), { status: 200 }),
    ))
    const { user } = renderStrictAt('/documentos/nuevo')
    await user.upload(screen.getByLabelText('Seleccionar documento PDF'), new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a procesamiento' }))

    await waitFor(() => {
      const postCalls = vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === 'POST')
      expect(postCalls).toHaveLength(1)
    })
  })

  it('comparte la misma Promise para llamadas concurrentes del mismo File y tipo', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify(successBody), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const file = new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' })

    const first = createLocalJob(file, 'budget')
    const second = createLocalJob(file, 'budget')

    expect(first).toBe(second)
    await first
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it('mantiene el éxito del mismo File y permite reintento tras un fallo', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error_code: 'PROCESSING_CAPACITY_BUSY' }), { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(successBody), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const file = new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' })

    await expect(createLocalJob(file)).rejects.toThrow('Hay otro documento procesándose')
    await createLocalJob(file)
    await createLocalJob(file)

    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })

  it('separa Files distintos y tipos documentales distintos', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify(successBody), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const firstFile = new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' })
    const secondFile = new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' })

    await Promise.all([
      createLocalJob(firstFile, 'budget'),
      createLocalJob(secondFile, 'budget'),
      createLocalJob(firstFile, 'invoice'),
    ])

    expect(fetchSpy).toHaveBeenCalledTimes(3)
    expect((fetchSpy.mock.calls[0][1]?.body as FormData).get('document_type')).toBe('budget')
    expect((fetchSpy.mock.calls[2][1]?.body as FormData).get('document_type')).toBe('invoice')
  })

  it('muestra el 503 de capacidad de forma segura y permite reintento manual', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error_code: 'PROCESSING_CAPACITY_BUSY' }), { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(successBody), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const { user } = renderStrictAt('/documentos/nuevo')
    await user.upload(screen.getByLabelText('Seleccionar documento PDF'), new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a procesamiento' }))

    expect(await screen.findByText('Hay otro documento procesándose. Espera a que termine antes de intentarlo nuevamente')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Intentar de nuevo' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Intentar de nuevo' }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2))
  })

  it.each([
    'LOCAL_MODE_DISABLED',
    'LOCAL_ONLY',
    'LOCAL_HEADER_REQUIRED',
    'INVALID_DOCUMENT_TYPE',
    'PAYLOAD_TOO_LARGE',
    'PROCESSING_CAPACITY_BUSY',
  ])('expone de forma controlada el error %s', async (code) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error_code: code }), { status: 403 }),
    ))

    await expect(createLocalJob(new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' })))
      .rejects.toEqual(expect.objectContaining({ code }))
  })

  it('mantiene las etiquetas de estados terminales compartidos', () => {
    expect(jobStatusLabels.COMPLETADO).toBe('Listo')
    expect(jobStatusLabels.REVISAR).toBe('Necesita revisión')
    expect(jobStatusLabels.ERROR).toBe('No se pudo procesar')
  })

  it('fija Vite al loopback y limita el proxy a la API local', () => {
    expect(viteConfigSource).toContain("host: '127.0.0.1'")
    expect(viteConfigSource).toContain('port: 5173')
    expect(viteConfigSource).toContain('strictPort: true')
    expect(viteConfigSource).toContain('port: 4173')
    expect(viteConfigSource).toContain("'/api': 'http://127.0.0.1:8000'")
    expect(viteConfigSource).not.toContain("host: '0.0.0.0'")
    expect(viteConfigSource).not.toContain('host: true')
    expect(viteConfigSource).not.toContain("'/v1'")
    expect(viteConfigSource).not.toContain("'/api/v1'")
    expect(viteConfigSource).not.toContain('cors')
  })

  it('consulta estado y descarga usando sólo el marcador local', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(successBody), { status: 200 }))
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)

    await getLocalJob('job-1')
    await downloadLocalJobResult('job-1')

    expect(fetchSpy).toHaveBeenNthCalledWith(1, '/api/v1/local/jobs/job-1', {
      headers: { 'X-Local-Pilot': '1' },
    })
    expect(fetchSpy).toHaveBeenNthCalledWith(2, '/api/v1/local/jobs/job-1/result', {
      headers: { 'X-Local-Pilot': '1' },
    })
    for (const [, request] of fetchSpy.mock.calls) {
      expect(request.headers).not.toHaveProperty('X-API-Key')
      expect(request.headers).not.toHaveProperty('X-Drive-File-Id')
    }
  })

  it.each([
    ['COMPLETADO', 'Excel listo'],
    ['REVISAR', 'Excel preliminar con observaciones'],
  ] as const)('revalida %s y muestra el copy local correcto', async (status, title) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        ...successBody,
        status,
        requires_review: status === 'REVISAR',
      }), { status: 200 }),
    ))

    renderAt('/documentos/local/job-1/resultado')

    expect(await screen.findByRole('heading', { name: title })).toBeVisible()
    const downloadButton = screen.getByRole('button', { name: 'Descargar Excel' })
    expect(downloadButton).toBeEnabled()
    expect(downloadButton).toHaveClass('button--primary')
    expect(screen.getByText(status === 'REVISAR'
      ? 'El Excel está disponible como resultado preliminar y contiene observaciones del procesamiento.'
      : 'El Excel generado está disponible para descargar.').closest('.inline-alert')).toHaveClass('inline-alert--success')
    expect(screen.getByLabelText('Progreso del proceso')).toHaveTextContent('Documento')
    expect(screen.getByLabelText('Progreso del proceso')).toHaveTextContent('Procesamiento')
    expect(screen.getByLabelText('Progreso del proceso')).toHaveTextContent('Revisión')
    expect(screen.getByLabelText('Progreso del proceso')).toHaveTextContent('Excel')
    expect(screen.getByLabelText('Progreso del proceso')).toHaveTextContent('Columnas')
  })

  it('descarga el Blob con nombre seguro y revoca la URL temporal', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(successBody), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'COMPLETADO' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const createObjectURL = vi.fn(() => 'blob:quipta-test')
    const revokeObjectURL = vi.fn()
    const OriginalURL = URL
    class TestURL extends OriginalURL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    }
    vi.stubGlobal('URL', TestURL)
    let downloadedName = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloadedName = this.download
    })
    const { user } = renderAt('/documentos/local/job-1/resultado')

    await user.click(await screen.findByRole('button', { name: 'Descargar Excel' }))

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1))
    expect(downloadedName).toBe('quipta-excel-job-1.xlsx')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:quipta-test')
    expect(fetchSpy).toHaveBeenLastCalledWith('/api/v1/local/jobs/job-1/export/result', {
      headers: { 'X-Local-Pilot': '1' },
    })
    expect(fetchSpy).toHaveBeenNthCalledWith(2, '/api/v1/local/jobs/job-1/export', { method: 'POST', headers: { 'X-Local-Pilot': '1' } })
  })

  it('muestra un error seguro y limpia la URL temporal si falla la descarga', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(successBody), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'COMPLETADO' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const createObjectURL = vi.fn(() => 'blob:quipta-failing-download')
    const revokeObjectURL = vi.fn()
    const OriginalURL = URL
    class TestURL extends OriginalURL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    }
    vi.stubGlobal('URL', TestURL)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      throw new Error('private browser details')
    })
    const { user } = renderAt('/documentos/local/job-1/resultado')

    await user.click(await screen.findByRole('button', { name: 'Descargar Excel' }))

    expect(await screen.findByText('No pudimos completar la operación. Inténtalo nuevamente.')).toBeVisible()
    expect(screen.queryByText('private browser details')).not.toBeInTheDocument()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:quipta-failing-download')
  })

  it('mantiene deshabilitada la descarga si el resultado no está disponible', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...successBody, result_available: false }), { status: 200 }),
    ))
    renderAt('/documentos/local/job-1/resultado')

    expect(await screen.findByText('El trabajo no tiene un archivo disponible para descargar.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeDisabled()
  })

  it('muestra la expiración informada al revalidar y mantiene la descarga deshabilitada', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        ...successBody,
        result_available: false,
        error_code: 'RESULT_EXPIRED',
      }), { status: 200 }),
    ))
    renderAt('/documentos/local/job-1/resultado')

    expect(await screen.findByText('El archivo ha expirado y ya no está disponible')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeDisabled()
  })

  it.each([
    [404, 'RESULT_NOT_FOUND', 'El archivo ya no está disponible'],
    [409, 'RESULT_NOT_READY', 'El archivo todavía no está disponible'],
  ])('muestra el error HTTP %s de forma sanitizada', async (status, code, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error_code: code, private_path: '/secret' }), { status }),
    ))
    renderAt('/documentos/local/job-1/resultado')

    expect(await screen.findByText(message)).toBeVisible()
    expect(screen.queryByText('/secret')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeDisabled()
  })

  it('muestra un error de red sanitizado', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('private network details')))
    renderAt('/documentos/local/job-1/resultado')

    expect(await screen.findByText('No se pudo conectar con la API local')).toBeVisible()
    expect(screen.queryByText('private network details')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeDisabled()
  })

  it('muestra el error de revisión si un localJob REVISAR recibe 409', async () => {
    const reviewJob = { ...successBody, status: 'REVISAR', requires_review: true }
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(reviewJob), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ error_code: 'RESULT_NOT_READY' }), { status: 409 }))
    vi.stubGlobal('fetch', fetchSpy)
    const { user } = renderAt('/documentos/nuevo')
    await user.upload(
      screen.getByLabelText('Seleccionar documento PDF'),
      new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' }),
    )
    await user.click(screen.getByRole('button', { name: 'Continuar a procesamiento' }))

    expect(await screen.findByText('El archivo todavía no está disponible')).toBeVisible()
    expect(window.location.pathname).toBe('/documentos/local/job-1/revision')
    expect(screen.queryByRole('button', { name: 'Continuar al Excel preliminar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Descargar Excel' })).not.toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })

  it('traduce un código conocido a un mensaje público', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error_code: 'STORAGE_ERROR' }), { status: 500 }),
    ))

    await expect(getLocalJob('job-1')).rejects.toThrow('No se pudo completar la solicitud')
  })

  it('usa el fallback público para un código desconocido', async () => {
    const internalCode = 'PRIVATE_INTERNAL_CODE'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error_code: internalCode }), { status: 500 }),
    ))

    await expect(getLocalJob('job-1')).rejects.toThrow('No pudimos completar la operación. Inténtalo nuevamente.')
    await expect(getLocalJob('job-1')).rejects.not.toThrow(internalCode)
  })

  it('habilita la descarga sólo después de completar una revalidación exitosa', async () => {
    let resolveStatus: ((response: Response) => void) | undefined
    const fetchSpy = vi.fn().mockImplementation(
      () => new Promise<Response>((resolve) => { resolveStatus = resolve }),
    )
    vi.stubGlobal('fetch', fetchSpy)
    renderAt('/documentos/local/job-1/resultado')

    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeDisabled()
    resolveStatus?.(new Response(JSON.stringify(successBody), { status: 200 }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeEnabled())
  })

  it('completa POST y navega a la revisión antes de permitir exportar', async () => {
    const emptyTable = { schema_version: '3', job_id: 'job-1', review_revision: 0,
      pending_decision_count: 0, filter: 'pending', offset: 0, limit: 25,
      total_count: 0, columns: [], rows: [] }
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(successBody), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(emptyTable), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const { user } = renderAt('/documentos/nuevo')
    await user.upload(screen.getByLabelText('Seleccionar documento PDF'), new File(['pdf'], 'presupuesto.pdf', { type: 'application/pdf' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a procesamiento' }))

    expect(await screen.findByRole('heading', { name: 'Revisión guiada' })).toBeVisible()
    expect(window.location.pathname).toBe('/documentos/local/job-1/revision')
    expect(screen.queryByRole('button', { name: 'Descargar Excel' })).not.toBeInTheDocument()
    expect(fetchSpy.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
  })

  it('limpia el trabajo local al iniciar otro documento', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(successBody), { status: 200 }),
    ))
    const { user } = renderAt('/documentos/local/job-1/resultado')
    await screen.findByRole('heading', { name: 'Excel listo' })
    await user.click(screen.getByRole('button', { name: 'Procesar otro documento' }))

    expect(window.location.pathname).toBe('/documentos/nuevo')
    expect(screen.getByRole('heading', { name: 'Sube tu presupuesto en PDF' })).toBeVisible()
    expect(screen.queryByText('presupuesto.pdf')).not.toBeInTheDocument()
  })
})
