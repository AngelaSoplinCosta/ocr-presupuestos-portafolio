import { useState } from 'react'
import { Button } from './Button'
import { LocalPdfViewer } from './LocalPdfViewer'
import { humanColumnLabel, humanFieldLabel } from './reviewLabels'
import type { LocalReviewDecision, LocalReviewRow, ReviewObservation, StructuredReviewField } from '../types'

function actionLabel(action: string, observation: ReviewObservation) {
  if (action === 'keep_original') return `Mantener “${observation.extracted_value || 'valor detectado'}”`
  if (action === 'accept_suggestion') return `Aceptar “${observation.suggestion?.value || 'sugerencia'}”`
  return observation.target?.scope === 'row' ? 'Registrar valor de revisión' : 'Editar valor'
}

function StructuredFieldCard({ field, observationId, onSave }: { field: StructuredReviewField; observationId: string; onSave: (decision: LocalReviewDecision) => void }) {
  const numericField = field.key === 'quantity' || field.key === 'unit_price' || field.key === 'amount'
  const numericClassName = numericField ? 'numeric-value' : undefined
  const edit = () => {
    const value = window.prompt(`Edita ${field.label}`, field.provisional_value)
    if (value?.trim()) onSave({ observation_id: observationId, action: 'set_value', field: field.key, value: value.trim() })
  }
  return <section className="structured-review-field" aria-label={`Revisión de ${field.label}`}>
    <div className="structured-review-field__heading"><h3>{field.label}</h3><span className={`review-status review-status--${field.state === 'RESOLVED' ? 'resolved' : 'pending'}`}>{field.state === 'RESOLVED' ? (field.decision?.action === 'confirm_provisional' ? 'Provisional confirmado' : 'Decisión guardada') : 'Pendiente'}</span></div>
    <dl><div><dt>OCR crudo</dt><dd className={numericClassName}>{field.ocr_value ?? 'OCR no separable'}</dd></div><div><dt>Valor provisional</dt><dd className={numericClassName}>{field.provisional_value || '—'}</dd></div><div><dt>Valor sugerido</dt><dd className={numericClassName}>{field.suggestion?.value ?? 'No se propuso un valor'}</dd></div></dl>
    {field.differs_from_ocr === true && <p className="structured-review-field__difference">El provisional difiere del OCR crudo.</p>}
    {field.differs_from_ocr === false && <p className="structured-review-field__match">El provisional coincide con el OCR crudo.</p>}
    {field.state === 'PENDING' && <div className="structured-review-field__actions">
      {field.manual_only ? <><p>OCR no separable: ingresa un valor manual válido para confirmar este campo.</p><Button variant="secondary" onClick={edit}>Editar {field.label}</Button></> : <><Button variant="secondary" onClick={() => onSave({ observation_id: observationId, action: 'keep_provisional', field: field.key })}>Conservar “{field.provisional_value || 'provisional'}”</Button>{field.suggestion && <Button onClick={() => onSave({ observation_id: observationId, action: 'accept_suggestion', field: field.key })}>Aceptar “{field.suggestion.value}”</Button>}<Button variant="quiet" onClick={edit}>Editar {field.label}</Button></>}
    </div>}
  </section>
}

export function LocalReviewDrawer({ jobId, observation, row, onSave }: { jobId: string; observation: ReviewObservation | null; row: LocalReviewRow | null; onSave: (decision: LocalReviewDecision) => void }) {
  const [confirming, setConfirming] = useState(false)
  if (!observation) return <aside className="review-drawer"><p>Selecciona una celda o fila resaltada para revisar la decisión.</p></aside>
  const structured = row?.structured_review?.observation_id === observation.id ? row.structured_review : null
  if (structured) {
    const safeCount = structured.fields.filter(field => field.can_confirm_provisional).length
    return <aside className="review-drawer review-drawer--structured" aria-live="polite"><h2>Revisar fila no separada</h2><p><strong>{structured.confirmed_field_count} de 6 campos confirmados</strong></p><section className="structured-review-evidence"><h3>Evidencia OCR original</h3><pre>{structured.raw_ocr_line}</pre><p>La evidencia original no se modifica. Revisa los campos antes de confirmar cambios.</p></section>{safeCount > 0 && !confirming && <Button onClick={() => setConfirming(true)}>Confirmar {safeCount} campos provisionales</Button>}{confirming && <section className="structured-review-confirm"><p>Se confirmarán {safeCount} campos provisionales. {structured.pending_field_count - safeCount} requieren revisión individual.</p><Button onClick={() => { setConfirming(false); onSave({ observation_id: structured.observation_id, action: 'confirm_provisional_row' }) }}>Confirmar campos provisionales</Button><Button variant="quiet" onClick={() => setConfirming(false)}>Cancelar</Button></section>}{structured.legacy_row_decision && <p className="structured-review-legacy">Decisión de fila anterior: {structured.legacy_row_decision.value}. Se conserva como evidencia y no modifica columnas.</p>}<div className="structured-review-fields">{structured.fields.map(field => <StructuredFieldCard key={field.key} field={field} observationId={structured.observation_id} onSave={onSave} />)}</div><LocalPdfViewer jobId={jobId} page={observation.page} /></aside>
  }
  const resolved = observation.state === 'RESOLVED'
  const manualOnly = observation.allowed_actions.length === 1 && observation.allowed_actions[0] === 'set_value'
  const rowScope = observation.target?.scope === 'row'
  return <aside className="review-drawer" aria-live="polite"><h2>{resolved ? 'Decisión guardada' : 'Revisar observación'}</h2><p><strong>{rowScope ? 'Revisión de fila no separada' : humanFieldLabel(observation.field)}</strong></p><dl className="review-drawer__comparison"><div><dt>Valor detectado</dt><dd>{observation.extracted_value || 'No disponible'}</dd></div><div><dt>Valor sugerido</dt><dd>{observation.suggestion?.value || 'No se propuso un valor'}</dd></div><div><dt>Motivo</dt><dd>{observation.reason}</dd></div><div><dt>Página</dt><dd>{observation.page ? `Página ${observation.page}` : 'No indicada'}</dd></div></dl>{rowScope && <p>Esta fila no fue separada con seguridad. Confirmarla no modifica columnas ni valores del Excel simple.</p>}{row && <dl className="review-drawer__values">{Object.entries(row.cells).map(([key, value]) => <div key={key}><dt>{humanColumnLabel({ key, label: key, data_type: 'text', included: true, position: 0, origin: 'standard' })}</dt><dd>{value || '—'}</dd></div>)}</dl>}<LocalPdfViewer jobId={jobId} page={observation.page} />{resolved ? <><p><strong>{observation.resolved_value}</strong></p>{rowScope && <p>La revisión de esta fila quedó confirmada; no modifica columnas ni separa automáticamente la fila.</p>}</> : <><p>{manualOnly && (rowScope ? 'Esta observación requiere un valor manual. Se registra para la revisión, pero no separa automáticamente la fila.' : 'Esta observación requiere que ingreses un valor manual.')}</p>{rowScope && !manualOnly && <p>La confirmación se registra para la revisión y no modifica columnas de esta fila.</p>}{observation.allowed_actions.includes('keep_original') && <Button variant="secondary" onClick={() => onSave({ observation_id: observation.id, action: 'keep_original' })}>{actionLabel('keep_original', observation)}</Button>}{observation.allowed_actions.includes('accept_suggestion') && <Button onClick={() => onSave({ observation_id: observation.id, action: 'accept_suggestion' })}>{actionLabel('accept_suggestion', observation)}</Button>}{observation.allowed_actions.includes('set_value') && <Button variant="quiet" onClick={() => { const value = window.prompt(rowScope ? 'Registra el valor para la revisión' : 'Escribe el valor corregido', observation.extracted_value); if (value?.trim()) onSave({ observation_id: observation.id, action: 'set_value', value: value.trim() }) }}>{actionLabel('set_value', observation)}</Button>}</>}</aside>
}
