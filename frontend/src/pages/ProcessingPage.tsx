import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { DemoBanner } from '../components/DemoBanner'
import { InlineAlert } from '../components/InlineAlert'
import { PageHeader } from '../components/PageHeader'
import { processingSteps } from '../data/demoData'
import { useApp } from '../hooks/useApp'
import { createLocalJob, LocalJobError } from '../api/localJobs'
import { jobStatusLabels, type Job } from '../types'

export function ProcessingPage() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  const [localJob, setLocalJob] = useState<Job | null>(null)
  const [localError, setLocalError] = useState('')
  const [retryAttempt, setRetryAttempt] = useState(0)
  const isLocalUpload = Boolean(state.file && !state.demo)

  useEffect(() => {
    if (!isLocalUpload || !state.file || state.processingComplete) return
    let active = true
    createLocalJob(state.file)
      .then((job) => {
        if (!active) return
        setLocalJob(job)
        if (job.status === 'COMPLETADO' || job.status === 'REVISAR') {
          dispatch({ type: 'SET_LOCAL_JOB', job })
          dispatch({ type: 'MARK_PROCESSED' })
          navigate(`/documentos/local/${job.job_id}/revision`, { replace: true })
        } else if (job.status === 'ERROR') {
          setLocalError('No se pudo procesar el documento')
        }
      })
      .catch((error: unknown) => {
        if (!active) return
        setLocalError(error instanceof LocalJobError ? error.message : 'INTERNAL_ERROR')
      })
    return () => { active = false }
  }, [dispatch, isLocalUpload, navigate, retryAttempt, state.file, state.processingComplete])

  if (!state.file && !state.demo) return <Navigate to="/documentos/nuevo" replace />

  const showDetectedInformation = () => dispatch({ type: 'MARK_PROCESSED' })
  return (
    <div className="flow-page narrow-page">
      {state.demo && <DemoBanner />}
      <PageHeader title={isLocalUpload ? 'Procesando documento' : 'Procesamiento simulado'} description={isLocalUpload ? 'El motor está leyendo el PDF y comprobando sus partidas. Después podrás revisarlas.' : 'Recorre un ejemplo de las etapas sin cargar un PDF.'} eyebrow={isLocalUpload ? 'Paso 2 de 5' : 'Paso 2 de 5'} />
      {state.demo ? <InlineAlert title="Sólo demostración" tone="warning">Demostración: esta pantalla todavía no está conectada al motor de procesamiento.</InlineAlert> : <InlineAlert title={localError ? 'No se pudo conectar con la API local' : 'Conexión local'} tone={localError ? 'error' : 'info'}>{localError || (localJob ? `Estado: ${jobStatusLabels[localJob.status]}` : 'Enviando el PDF a la API local.')}</InlineAlert>}
      {state.demo && <ol className="processing-list">
        {processingSteps.map((step, index) => <li key={step}><span aria-hidden="true">{index + 1}</span><div><strong>{step}</strong><p>Etapa representada con datos ficticios.</p></div></li>)}
      </ol>}
      {state.demo && <p className="no-time-limit">No hay límite de tiempo ni avance automático.</p>}
      {isLocalUpload ? (
        localError ? <div className="flow-actions"><Button onClick={() => { setLocalError(''); setLocalJob(null); setRetryAttempt((attempt) => attempt + 1) }}>Intentar de nuevo</Button></div> : <div className="flow-actions"><Button disabled>{localJob ? 'Preparando resultado' : 'Enviando documento'}</Button></div>
      ) : !state.processingComplete ? (
        <div className="flow-actions"><Button onClick={showDetectedInformation}>Mostrar información detectada</Button></div>
      ) : (
        <>
          <InlineAlert title="Información ficticia disponible" tone="success">Se cargaron 9 campos de ejemplo únicamente en memoria. Ningún PDF real fue leído ni procesado.</InlineAlert>
          <div className="flow-actions"><Button onClick={() => navigate('/documentos/nuevo/columnas')}>Continuar a columnas</Button></div>
        </>
      )}
    </div>
  )
}
