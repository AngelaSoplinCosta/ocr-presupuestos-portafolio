import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { DemoBanner } from '../components/DemoBanner'
import { InlineAlert } from '../components/InlineAlert'
import { PageHeader } from '../components/PageHeader'
import { ReviewPanel } from '../components/ReviewPanel'
import { LocalTabularReviewPage } from '../components/LocalReviewTable'
import { observations } from '../data/demoData'
import { useApp } from '../hooks/useApp'
import { getLocalJobReview, LocalJobError, saveLocalDecisions } from '../api/localJobs'
import type { LocalReview } from '../types'

type Filter = 'pending' | 'resolved' | 'all'

function DemoReviewPage() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('pending')
  const [activeId, setActiveId] = useState(observations[0].id)
  const [mobileView, setMobileView] = useState<'evidence' | 'review'>('review')
  const [locationMessage, setLocationMessage] = useState('')

  if (!state.file && !state.demo) return <Navigate to="/documentos/nuevo" replace />
  if (!state.processingComplete) return <Navigate to="/documentos/nuevo/procesamiento" replace />
  if (!state.columnsConfirmed) return <Navigate to="/documentos/nuevo/columnas" replace />

  const relevantObservations = observations.filter((observation) => observation.critical || state.columns.some((column) => column.included && column.linkedField === observation.linkedField))

  const pending = relevantObservations.filter((observation) => !state.decisions[observation.id]).length
  const filtered = relevantObservations.filter((observation) => filter === 'all' || (filter === 'pending' ? !state.decisions[observation.id] : Boolean(state.decisions[observation.id])))
  const justResolved = filter === 'pending' ? relevantObservations.find((observation) => observation.id === activeId && state.decisions[observation.id]) : undefined
  const visible = justResolved ? [justResolved, ...filtered] : filtered
  const active = visible.find((observation) => observation.id === activeId) ?? visible[0] ?? relevantObservations[0]
  const activeIndex = visible.findIndex((observation) => observation.id === active.id)
  const progress = relevantObservations.length - pending

  const move = (offset: number) => {
    const next = visible[activeIndex + offset]
    if (next) { setActiveId(next.id); setLocationMessage('') }
  }

  return (
    <div className="flow-page review-page">
      <DemoBanner />
      <PageHeader title="Revisa las observaciones" description="Compara la evidencia y decide qué valor conservar. Ninguna sugerencia se aplica por sí sola." eyebrow="Paso 4 de 5" />
      <div className="review-toolbar">
        <div><strong>{pending} pendientes</strong><span>{progress} de {relevantObservations.length} revisadas</span><progress value={progress} max={relevantObservations.length}>{progress} de {relevantObservations.length}</progress></div>
        <div className="segmented" aria-label="Filtrar observaciones">
          <Button variant={filter === 'pending' ? 'primary' : 'quiet'} onClick={() => setFilter('pending')}>Pendientes</Button>
          <Button variant={filter === 'resolved' ? 'primary' : 'quiet'} onClick={() => setFilter('resolved')}>Resueltas</Button>
          <Button variant={filter === 'all' ? 'primary' : 'quiet'} onClick={() => setFilter('all')}>Todas</Button>
        </div>
      </div>

      <p className="large-screen-hint">Para comparar más información al mismo tiempo, puedes utilizar una pantalla más grande.</p>
      <div className="mobile-review-toggle" aria-label="Sección visible">
        <Button variant={mobileView === 'evidence' ? 'primary' : 'secondary'} onClick={() => setMobileView('evidence')}>Ver documento</Button>
        <Button variant={mobileView === 'review' ? 'primary' : 'secondary'} onClick={() => setMobileView('review')}>Revisar dato</Button>
      </div>

      {visible.length === 0 ? (
        <InlineAlert title={filter === 'pending' ? 'No quedan observaciones pendientes' : 'No hay observaciones en este filtro'} tone="success">Puedes cambiar el filtro o continuar al resultado cuando todo esté revisado.</InlineAlert>
      ) : (
        <div className="review-workspace">
          <section className={`evidence-panel ${mobileView === 'review' ? 'mobile-hidden' : ''}`} aria-labelledby="evidence-title">
            <div className="evidence-panel__top"><div><p className="eyebrow">Representación de ejemplo</p><h2 id="evidence-title">Evidencia documental</h2></div><span>Página {active.page}</span></div>
            <div className="fake-document" aria-label={`Fragmento ficticio de la página ${active.page}`}><div className="fake-document__line" /><div className="fake-document__line short" /><mark>{active.evidence}</mark><div className="fake-document__line" /><div className="fake-document__line medium" /></div>
            <p className="evidence-note">Esta representación no proviene de un PDF real.</p>
            <Button variant="secondary" onClick={() => setLocationMessage(`Ubicación mostrada: página ${active.page}, fragmento resaltado.`)}>Ver ubicación</Button>
            <p role="status" aria-live="polite">{locationMessage}</p>
          </section>
          <div className={`review-detail ${mobileView === 'evidence' ? 'mobile-hidden' : ''}`}>
            <ReviewPanel key={active.id} observation={active} decision={state.decisions[active.id]} onDecision={(decision) => dispatch({ type: 'SET_DECISION', observationId: active.id, decision })} onUndo={() => dispatch({ type: 'UNDO_DECISION', observationId: active.id })} />
          </div>
        </div>
      )}

      {visible.length > 0 && <div className="pager" aria-label="Navegar observaciones"><Button variant="quiet" onClick={() => move(-1)} disabled={activeIndex <= 0}>← Anterior</Button><span>{activeIndex + 1} de {visible.length}</span><Button variant="quiet" onClick={() => move(1)} disabled={activeIndex >= visible.length - 1}>Siguiente →</Button></div>}

      <div className="sticky-actions review-footer">
        <Button variant="secondary" onClick={() => dispatch({ type: 'LOAD_EXAMPLE_DECISIONS', observationIds: relevantObservations.map((item) => item.id), suggestions: relevantObservations.map((item) => item.suggested) })}>Cargar decisiones de ejemplo</Button>
        <div><span className="pending-note" aria-live="polite">{pending ? `Revisa ${pending} ${pending === 1 ? 'observación' : 'observaciones'} antes de finalizar.` : 'Todas las observaciones están resueltas.'}</span><Button onClick={() => navigate('/documentos/demo/resultado')} disabled={pending > 0}>Finalizar revisión</Button></div>
      </div>
    </div>
  )
}

function safeLocalError(error: unknown) {
  return error instanceof LocalJobError ? error.message : 'No pudimos completar la operación. Inténtalo nuevamente.'
}

function LocalReviewPage({ jobId }: { jobId: string }) {
  const navigate = useNavigate()
  const [review, setReview] = useState<LocalReview | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    getLocalJobReview(jobId, offset).then((payload) => {
      if (active) setReview(payload)
    }).catch((requestError: unknown) => {
      if (active) setError(safeLocalError(requestError))
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [jobId, offset])

  return <div className="flow-page review-page">
    <PageHeader title="Encontramos datos que necesitan tu revisión." description="Revisa estas observaciones antes de utilizar el Excel. Las sugerencias no se aplicaron automáticamente." eyebrow="Paso 3 de 4 · Revisión" />
    {loading && <InlineAlert title="Cargando revisión" tone="info">Consultando las observaciones detectadas en el documento.</InlineAlert>}
    {!loading && error && <InlineAlert title="No se pudo obtener la revisión" tone="error">{error}</InlineAlert>}
    {!loading && review && <>
      <InlineAlert title="Revisión disponible" tone="success">{review.pending_decision_count} decisiones pendientes de {review.requires_decision_count} requeridas.</InlineAlert>
      <p><strong>{review.total_count} observaciones</strong></p>
      <div className="review-workspace">
        <section className="review-detail" aria-label="Observaciones reales">
          {review.observations.map((item) => {
            const allowedActions = new Set(item.allowed_actions)
            const manualOnly = item.requires_decision && allowedActions.size === 1 && allowedActions.has('set_value')
            return <article key={item.id} className="review-panel">
            <div className="review-panel__heading"><div><span className="eyebrow">{item.page ? `Página ${item.page}` : 'Documento'}</span><h2>{item.field}</h2></div>{item.suggestion && <span className="confidence confidence--media">Confianza {item.suggestion.confidence}</span>}</div>
            <p className="review-context">{item.row.label || 'Validaciones del documento'}{item.row.order !== null ? ` · Fila ${item.row.order}` : ''}</p>
            <dl className="value-comparison"><div><dt>Valor detectado</dt><dd>{item.extracted_value || 'No disponible'}</dd></div>{item.suggestion ? <div><dt>Valor sugerido</dt><dd>{item.suggestion.value}</dd></div> : <div><dt>Sugerencia</dt><dd>Revisa este dato en el documento original.</dd></div>}<div><dt>Motivo</dt><dd>{item.reason}</dd></div></dl>
            {item.evidence.map((evidence) => <p key={evidence} className="review-context">{evidence}</p>)}
            {manualOnly && <p className="review-context">Esta observación requiere que ingreses un valor manual.</p>}
            {item.requires_decision && <div className="button-row">
              {allowedActions.has('keep_original') && <Button variant="secondary" onClick={() => saveLocalDecisions(jobId, review.review_revision, [{ observation_id: item.id, action: 'keep_original' }]).then(() => getLocalJobReview(jobId).then(setReview)).catch((requestError: unknown) => setError(safeLocalError(requestError)))}>Mantener original</Button>}
              {allowedActions.has('accept_suggestion') && <Button onClick={() => saveLocalDecisions(jobId, review.review_revision, [{ observation_id: item.id, action: 'accept_suggestion' }]).then(() => getLocalJobReview(jobId).then(setReview)).catch((requestError: unknown) => setError(safeLocalError(requestError)))}>Aceptar sugerencia</Button>}
            </div>}
            {item.requires_decision && allowedActions.has('set_value') && <Button variant="quiet" onClick={() => { const value = window.prompt('Escribe el valor corregido', item.extracted_value); if (value !== null) saveLocalDecisions(jobId, review.review_revision, [{ observation_id: item.id, action: 'set_value', value }]).then(() => getLocalJobReview(jobId, offset).then(setReview)).catch((requestError: unknown) => setError(safeLocalError(requestError))) }}>Editar valor</Button>}
          </article>
          })}</section>
      </div>
      {review.total_count > review.limit && <div className="pager"><Button variant="quiet" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - review.limit))}>← Anterior</Button><span>{offset + 1}–{Math.min(offset + review.limit, review.total_count)} de {review.total_count}</span><Button variant="quiet" disabled={offset + review.limit >= review.total_count} onClick={() => setOffset(offset + review.limit)}>Siguiente →</Button></div>}
      <div className="sticky-actions review-footer"><div><span className="pending-note">Las observaciones informativas no bloquean el Excel.</span><Button onClick={() => navigate(`/documentos/local/${jobId}/columnas`)} disabled={review.pending_decision_count > 0}>Continuar a columnas</Button></div></div>
    </>}
  </div>
}

void LocalReviewPage

export function ReviewPage() {
  const { jobId } = useParams()
  return jobId ? <LocalTabularReviewPage key={jobId} jobId={jobId} /> : <DemoReviewPage />
}
