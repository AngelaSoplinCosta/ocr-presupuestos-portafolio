import { useState } from 'react'
import type { Decision, Observation } from '../types'
import { Button } from './Button'
import { HelpDisclosure } from './HelpDisclosure'

function isValidValue(field: string, value: string) {
  if (field === 'Parcial') return /^S\/\s?\d{1,3}(,\d{3})*\.\d{2}$/.test(value)
  if (field === 'Metrado') return /^\d+(\.\d{1,2})?$/.test(value)
  return value.trim().length > 0 && value.trim().length <= 20
}

export function ReviewPanel({ observation, decision, onDecision, onUndo }: { observation: Observation; decision?: Decision; onDecision: (decision: Decision) => void; onUndo: () => void }) {
  const [editing, setEditing] = useState(false)
  const [manualValue, setManualValue] = useState('')
  const [error, setError] = useState('')

  const saveManual = () => {
    if (!isValidValue(observation.field, manualValue)) {
      setError(`Revisa el formato del valor para ${observation.field}. El valor original permanece sin cambios.`)
      return
    }
    onDecision({ kind: 'manual', value: manualValue.trim() })
    setEditing(false)
    setError('')
  }

  return (
    <article className="review-panel" aria-labelledby={`review-${observation.id}`}>
      <div className="review-panel__heading">
        <div><span className="eyebrow">Página {observation.page}{observation.critical ? ' · Incidencia general crítica' : ''}</span><h2 id={`review-${observation.id}`}>{observation.field}</h2></div>
        <span className={`confidence confidence--${observation.confidence.toLowerCase()}`}>Nivel {observation.confidence}</span>
      </div>
      <p className="review-context">{observation.context}</p>
      <dl className="value-comparison">
        <div><dt>Valor detectado</dt><dd>{observation.detected}</dd></div>
        <div><dt>Valor sugerido</dt><dd>{observation.suggested}</dd></div>
        <div><dt>Motivo</dt><dd>{observation.reason}</dd></div>
      </dl>

      {decision && (
        <div className="decision-summary" role="status" aria-label="Decisión aplicada">
          <span aria-hidden="true">✓</span>
          <div><strong>Decisión aplicada</strong><p>{decision.value}</p></div>
          <Button type="button" variant="quiet" onClick={onUndo}>Deshacer decisión</Button>
        </div>
      )}

      {!decision && !editing && (
        <div className="review-actions" aria-label="Decidir valor">
          <Button type="button" onClick={() => onDecision({ kind: 'suggested', value: observation.suggested })}>Confirmar sugerencia</Button>
          <Button type="button" variant="secondary" onClick={() => onDecision({ kind: 'detected', value: observation.detected })}>Conservar valor detectado</Button>
          <Button type="button" variant="quiet" onClick={() => { setEditing(true); setManualValue(observation.detected) }}>Editar manualmente</Button>
        </div>
      )}

      {!decision && editing && (
        <div className="manual-editor">
          <p>Original: <strong>{observation.detected}</strong></p>
          <label htmlFor={`manual-${observation.id}`}>Nuevo valor</label>
          <input id={`manual-${observation.id}`} value={manualValue} onChange={(event) => setManualValue(event.target.value)} aria-invalid={Boolean(error)} aria-describedby={`manual-error-${observation.id}`} />
          <p id={`manual-error-${observation.id}`} className="field-error" role="alert">{error}</p>
          <div className="button-row"><Button type="button" onClick={saveManual}>Aplicar valor</Button><Button type="button" variant="quiet" onClick={() => { setEditing(false); setError('') }}>Cancelar edición</Button></div>
        </div>
      )}

      <div className="review-help">
        <HelpDisclosure question="¿Por qué debo revisar este dato?">Porque existe una diferencia que puede cambiar el resultado. Tú decides qué valor conservar.</HelpDisclosure>
        <HelpDisclosure question="¿Dónde se encontró?">En la página {observation.page}, dentro de “{observation.context}”.</HelpDisclosure>
        <HelpDisclosure question="¿Qué ocurre si conservo el valor detectado?">Se mantiene el valor original tal como se presenta en esta demostración. Ninguna sugerencia se aplica automáticamente.</HelpDisclosure>
      </div>
    </article>
  )
}
