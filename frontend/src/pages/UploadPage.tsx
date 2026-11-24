import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { FileDropzone } from '../components/FileDropzone'
import { useApp } from '../hooks/useApp'
import type { DocumentType } from '../types'

const types: DocumentType[] = ['Presupuesto de obra']
const progressSteps = ['Documento', 'Procesamiento', 'Revisión', 'Columnas', 'Excel']

function FlowIcon({ name }: { name: 'document' | 'data' | 'column' | 'drive' }) {
  const paths = {
    document: <><path d="M6 2.75h7l5 5v13.5H6z" /><path d="M13 2.75v5h5M9 12h6M9 16h6" /></>,
    data: <><circle cx="12" cy="12" r="8.25" /><path d="M9 9.25h6M9 12h6M9 14.75h3.5" /></>,
    column: <><rect x="3.75" y="5" width="16.5" height="14" rx="1.5" /><path d="M9.25 5v14M14.75 5v14" /></>,
    drive: <><rect x="3.5" y="5.25" width="17" height="13.5" rx="2" /><path d="M6.5 14.75h11M16.75 11.25h.01" /></>,
  }

  return <svg className="upload-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

export function UploadPage() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  const [absenceError, setAbsenceError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const continueFlow = () => {
    if (!state.file) { setAbsenceError('Selecciona un PDF para continuar. Ninguna información se ha perdido.'); return }
    if (submitting) return
    setSubmitting(true)
    navigate('/documentos/nuevo/procesamiento')
  }

  return (
    <div className="upload-page">
      <header className="upload-intro">
        <h1 data-page-title tabIndex={-1}>Sube tu presupuesto en PDF</h1>
        <p>PDF escaneado o digital · Máximo 50 MB</p>
      </header>

      <section className="upload-mobile-progress" aria-labelledby="upload-progress-title">
        <h2 id="upload-progress-title">Tu avance</h2>
        <ol className="upload-progress-list" aria-label="Progreso del proceso">
          {progressSteps.map((step, index) => (
            <li key={step} className={index === 0 ? 'is-current' : ''}>
              <span aria-hidden="true"><i /></span>
              <b><span className="upload-progress-label" aria-hidden="true">{step}</span><span className="sr-only">{step}</span></b>
              {index < progressSteps.length - 1 && <em aria-hidden="true" />}
            </li>
          ))}
        </ol>
      </section>

      <div className="upload-layout">
        <section className="upload-main" aria-labelledby="upload-zone-title">
          <h2 id="upload-zone-title" className="sr-only">Carga tu documento</h2>
          <FileDropzone file={state.file} onFile={(file) => { dispatch({ type: 'SET_FILE', file }); setAbsenceError('') }} />
          <p className="upload-after-note">Después procesaremos el documento y prepararemos el Excel.</p>
          <div className="upload-local-note" role="status">
            <FlowIcon name="drive" />
            <span><strong>Procesamiento en este equipo</strong><small>Al continuar, el PDF se envía a la API local. Se conserva temporalmente para que puedas compararlo con las partidas extraídas; recargar la página no elimina esa copia.</small></span>
          </div>

          <div className="upload-preview" aria-label="Del documento al Excel">
            <span><FlowIcon name="document" /><b>Documento</b></span>
            <i aria-hidden="true" />
            <span><FlowIcon name="data" /><b>Procesamiento</b></span>
            <i aria-hidden="true" />
            <span><FlowIcon name="drive" /><b>Excel</b></span>
          </div>

          <div className={`upload-flow-controls ${state.file || absenceError ? 'is-visible' : ''}`}>
            <div className="form-field upload-type-field">
              <label htmlFor="document-type">Tipo documental sugerido</label>
              <select id="document-type" value={state.documentType} onChange={(event) => dispatch({ type: 'SET_DOCUMENT_TYPE', value: event.target.value as DocumentType })}>{types.map((type) => <option key={type}>{type}</option>)}</select>
            </div>
            <p className="field-error" role={absenceError ? 'alert' : undefined} aria-live={absenceError ? 'assertive' : undefined}>{absenceError}</p>
            <div className="flow-actions"><Button onClick={continueFlow} disabled={submitting}>{submitting ? 'Enviando documento' : 'Continuar a procesamiento'}</Button></div>
          </div>
        </section>

        <aside className="upload-next-steps" aria-labelledby="next-steps-title">
          <div className="upload-next-steps__content">
            <h2 id="next-steps-title">Así se preparará el Excel</h2>
            <p>Tu recorrido desde el PDF hasta la descarga:</p>
            <ol>
              <li><span aria-hidden="true">1</span><strong>Documento seleccionado</strong></li>
              <li><span aria-hidden="true">2</span><strong>Procesamiento local</strong></li>
              <li><span aria-hidden="true">3</span><strong>Revisión de datos dudosos</strong></li>
              <li><span aria-hidden="true">4</span><strong>Selección de columnas</strong></li>
              <li><span aria-hidden="true">5</span><strong>Descarga del Excel</strong></li>
            </ol>
          </div>
          <details className="upload-help">
            <summary>¿Qué ocurrirá después?</summary>
            <div><p>1. Validaremos el PDF.</p><p>2. Extraeremos las partidas.</p><p>3. Revisarás los datos dudosos antes de descargar el Excel.</p></div>
          </details>
        </aside>
      </div>
    </div>
  )
}
