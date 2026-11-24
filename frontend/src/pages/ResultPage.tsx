import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { downloadLocalJobResult, downloadLocalSimpleExport, generateLocalExport, getLocalJob, LOCAL_ERROR_FALLBACK, LocalJobError } from '../api/localJobs'
import { Button } from '../components/Button'
import { DemoBanner } from '../components/DemoBanner'
import { InlineAlert } from '../components/InlineAlert'
import { PageHeader } from '../components/PageHeader'
import { demoRows, observations } from '../data/demoData'
import type { ColumnDefinition, Job } from '../types'
import { useApp } from '../hooks/useApp'

function previewValue(column: ColumnDefinition, row: Record<string, string>) {
  if (column.origin === 'fixed') return column.fixedValue ?? ''
  if (column.origin === 'blank') return ''
  return column.linkedField ? row[column.linkedField] ?? '' : ''
}

function safeLocalError(error: unknown) {
  return error instanceof LocalJobError ? error.message : LOCAL_ERROR_FALLBACK
}

function LocalResult({ jobId }: { jobId: string }) {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  const initialJob = state.localJob?.job_id === jobId ? state.localJob : null
  const [job, setJob] = useState<Job | null>(initialJob)
  const [revalidatedJob, setRevalidatedJob] = useState<Job | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    getLocalJob(jobId)
      .then((currentJob) => {
        if (!active) return
        setJob(currentJob)
        setRevalidatedJob(currentJob)
        dispatch({ type: 'SET_LOCAL_JOB', job: currentJob })
      })
      .catch((requestError: unknown) => {
        if (active) {
          setRevalidatedJob(null)
          setError(safeLocalError(requestError))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [dispatch, jobId])

  const available = Boolean(
    !loading
      && !error
      && revalidatedJob?.job_id === jobId
      && !revalidatedJob.error_code
      && revalidatedJob.result_available
      && (revalidatedJob.status === 'COMPLETADO' || revalidatedJob.status === 'REVISAR'),
  )

  const download = async () => {
    if (!available || downloading) return
    setDownloading(true)
    setError('')
    let objectUrl: string | null = null
    let link: HTMLAnchorElement | null = null
    try {
      await generateLocalExport(jobId)
      const blob = await downloadLocalSimpleExport(jobId)
      objectUrl = URL.createObjectURL(blob)
      link = document.createElement('a')
      link.href = objectUrl
      link.download = `quipta-excel-${jobId}.xlsx`
      document.body.appendChild(link)
      link.click()
    } catch (requestError: unknown) {
      setError(safeLocalError(requestError))
    } finally {
      link?.remove()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setDownloading(false)
    }
  }

  const downloadTechnical = async () => {
    if (!available || downloading) return
    setDownloading(true); setError('')
    let objectUrl: string | null = null; let link: HTMLAnchorElement | null = null
    try { const blob = await downloadLocalJobResult(jobId); objectUrl = URL.createObjectURL(blob); link = document.createElement('a'); link.href = objectUrl; link.download = `quipta-trazabilidad-${jobId}.xlsx`; document.body.appendChild(link); link.click() }
    catch (requestError: unknown) { setError(safeLocalError(requestError)) }
    finally { link?.remove(); if (objectUrl) URL.revokeObjectURL(objectUrl); setDownloading(false) }
  }

  const restart = () => {
    dispatch({ type: 'RESET_PROCESS' })
    navigate('/documentos/nuevo')
  }

  const title = job?.status === 'REVISAR'
    ? 'Excel preliminar con observaciones'
    : job?.status === 'COMPLETADO'
      ? 'Excel listo'
      : 'Resultado local'
  const availabilityError = error || (
    job?.error_code === 'RESULT_EXPIRED'
      ? 'El archivo ha expirado y ya no está disponible'
      : ''
  )

  return (
    <div className="flow-page narrow-page">
      <PageHeader
        title={title}
        description="Resultado generado por el procesamiento local del PDF."
        eyebrow="Paso 5 de 5 · Excel"
      />
      {loading && <InlineAlert title="Revalidando resultado" tone="info">Confirmando que el archivo continúa disponible.</InlineAlert>}
      {!loading && available && (
        <InlineAlert title={title} tone="success">
          {job?.status === 'REVISAR'
            ? 'El Excel está disponible como resultado preliminar y contiene observaciones del procesamiento.'
            : 'El Excel generado está disponible para descargar.'}
        </InlineAlert>
      )}
      {!loading && !available && !availabilityError && (
        <InlineAlert title="Excel no disponible" tone="warning">
          El trabajo no tiene un archivo disponible para descargar.
        </InlineAlert>
      )}
      {availabilityError && <InlineAlert title="No se pudo obtener el resultado" tone="error">{availabilityError}</InlineAlert>}
      {job && (
        <dl className="result-summary">
          <div><dt>Documento</dt><dd>{job.original_filename}</dd></div>
          <div><dt>Estado</dt><dd>{title}</dd></div>
        </dl>
      )}
      <div className="download-area" aria-labelledby="download-title">
        <h2 id="download-title">Descarga</h2>
        <p>El archivo corresponde directamente al resultado generado por el procesamiento local.</p>
        <div className="button-row">
          <Button onClick={download} disabled={loading || downloading || !available}>
            {downloading ? 'Preparando descarga' : 'Descargar Excel'}
          </Button>
          <Button variant="secondary" onClick={downloadTechnical} disabled={loading || downloading || !available}>Descargar trazabilidad técnica</Button>
        </div>
      </div>
      <div className="flow-actions"><Button onClick={restart}>Procesar otro documento</Button></div>
    </div>
  )
}

function DemoResult() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  if (!state.file && !state.demo) return <Navigate to="/documentos/nuevo" replace />
  if (!state.processingComplete) return <Navigate to="/documentos/nuevo/procesamiento" replace />
  if (!state.columnsConfirmed) return <Navigate to="/documentos/nuevo/columnas" replace />
  const relevantObservations = observations.filter((observation) => observation.critical || state.columns.some((column) => column.included && column.linkedField === observation.linkedField))
  if (!relevantObservations.every((item) => state.decisions[item.id])) return <Navigate to="/documentos/demo/revision" replace />
  const selectedColumns = state.columns.filter((column) => column.included).sort((a, b) => a.position - b.position)

  const restart = () => {
    navigate('/documentos/nuevo')
    window.setTimeout(() => dispatch({ type: 'RESET_PROCESS' }), 0)
  }
  return (
    <div className="flow-page narrow-page">
      <DemoBanner />
      <PageHeader title="Documento preparado" description="Consulta el resumen ficticio de las decisiones tomadas durante el recorrido." eyebrow="Paso 5 de 5 · Resultado de ejemplo" />
      <InlineAlert title="Resultado de ejemplo" tone="success">Este resumen es demostrativo y no proviene del procesamiento de un documento real.</InlineAlert>
      <dl className="result-summary">
        <div><dt>Registros encontrados</dt><dd>48</dd></div>
        <div><dt>Observaciones revisadas</dt><dd>{relevantObservations.length}</dd></div>
        <div><dt>Filas no incorporadas</dt><dd>2</dd></div>
        <div><dt>Conciliación</dt><dd>Requiere comprobación humana</dd></div>
        <div><dt>Columnas elegidas</dt><dd>{selectedColumns.map((column) => column.label).join(', ')}</dd></div>
        <div><dt>Plantilla utilizada</dt><dd>{state.templateMessage ? 'Plantilla de esta demostración' : 'Configuración personalizada de ejemplo'}</dd></div>
      </dl>
      <section className="result-preview" aria-labelledby="result-preview-title">
        <div className="section-heading"><div><p className="eyebrow">Vista previa ficticia</p><h2 id="result-preview-title">Así quedará tu archivo</h2></div></div>
        <div className="table-wrap result-preview__table">
          <table>
            <thead><tr>{selectedColumns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
            <tbody>{demoRows.map((row, rowIndex) => <tr key={rowIndex}>{selectedColumns.map((column) => <td key={column.key}>{previewValue(column, row) || <span className="empty-value">Vacío</span>}</td>)}</tr>)}</tbody>
          </table>
        </div>
        <ol className="result-preview__cards">
          {demoRows.map((row, rowIndex) => (
            <li key={rowIndex}><h3>Fila {rowIndex + 1}</h3><dl>{selectedColumns.map((column) => <div key={column.key}><dt>{column.label}</dt><dd>{previewValue(column, row) || <span className="empty-value">Vacío</span>}</dd></div>)}</dl></li>
          ))}
        </ol>
      </section>
      <div className="download-area" aria-labelledby="download-title"><h2 id="download-title">Descargas</h2><p>La descarga estará disponible cuando conectemos el motor.</p><div className="button-row"><Button disabled>Descargar Excel</Button><Button variant="secondary" disabled>Descargar CSV</Button></div></div>
      <div className="flow-actions"><Button onClick={restart}>Procesar otro documento</Button></div>
    </div>
  )
}

export function ResultPage() {
  const { jobId } = useParams()
  return jobId ? <LocalResult key={jobId} jobId={jobId} /> : <DemoResult />
}
