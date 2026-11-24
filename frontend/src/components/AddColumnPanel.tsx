import { useId, useState, type FormEvent } from 'react'
import { detectedFields } from '../data/demoData'
import type { ColumnDefinition } from '../types'
import { Button } from './Button'

type CompletionMode = 'detected' | 'fixed' | 'blank'

export function AddColumnPanel({ columns, onAdd, onCancel }: { columns: ColumnDefinition[]; onAdd: (column: ColumnDefinition) => void; onCancel: () => void }) {
  const errorId = useId()
  const [name, setName] = useState('')
  const [mode, setMode] = useState<CompletionMode>('detected')
  const availableFields = detectedFields.filter((field) => !columns.some((column) => column.linkedField === field.key))
  const [linkedField, setLinkedField] = useState(availableFields[0]?.key ?? '')
  const [fixedValue, setFixedValue] = useState('')
  const [error, setError] = useState('')
  const selectedField = detectedFields.find((field) => field.key === linkedField)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const label = name.trim()
    if (!label) { setError('Escribe un nombre para la columna. La configuración actual se conserva.'); return }
    if (columns.some((column) => column.label.trim().toLocaleLowerCase('es') === label.toLocaleLowerCase('es'))) { setError('Ya existe una columna con ese nombre. Utiliza un nombre diferente.'); return }
    if (mode === 'detected' && !linkedField) { setError('Selecciona uno de los campos ficticios disponibles.'); return }
    if (mode === 'fixed' && !fixedValue.trim()) { setError('Escribe el valor que se repetirá en todas las filas.'); return }

    const baseKey = label.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'columna'
    let key = `user_${baseKey}`
    let suffix = 2
    while (columns.some((column) => column.key === key)) { key = `user_${baseKey}_${suffix}`; suffix += 1 }
    onAdd({
      key,
      defaultLabel: label,
      label,
      included: true,
      detail: mode === 'detected' ? `Vinculada con el campo ficticio ${selectedField?.label}.` : mode === 'fixed' ? 'Usa el mismo valor en todas las filas.' : 'Se deja vacía para completarla posteriormente.',
      origin: mode,
      position: columns.length,
      userCreated: true,
      fixedValue: mode === 'fixed' ? fixedValue.trim() : undefined,
      linkedField: mode === 'detected' ? linkedField : undefined,
    })
  }

  return (
    <section className="add-column-panel" aria-labelledby="add-column-title">
      <h2 id="add-column-title">Añadir una columna</h2>
      <p>La columna se añadirá al final y permanecerá únicamente durante esta sesión.</p>
      <form onSubmit={submit} noValidate>
        <div className="form-field">
          <label htmlFor="new-column-name">Nombre de la columna</label>
          <input id="new-column-name" value={name} maxLength={60} onChange={(event) => { setName(event.target.value); setError('') }} aria-describedby={`new-column-help ${errorId}`} aria-invalid={Boolean(error)} />
          <small id="new-column-help">Obligatorio. Máximo 60 caracteres y sin duplicar un nombre existente.</small>
        </div>
        <fieldset className="radio-group">
          <legend>¿Cómo quieres completar esta columna?</legend>
          <label><input type="radio" name="completion" checked={mode === 'detected'} onChange={() => { setMode('detected'); setError('') }} /> <span><strong>Usar información detectada</strong><small>Vincula uno de los campos ficticios disponibles.</small></span></label>
          {mode === 'detected' && (
            <div className="nested-field form-field">
              <label htmlFor="detected-field">Campo detectado</label>
              <select id="detected-field" value={linkedField} onChange={(event) => setLinkedField(event.target.value)} disabled={!availableFields.length}>
                {!availableFields.length && <option value="">No quedan campos disponibles</option>}
                {availableFields.map((field) => <option key={field.key} value={field.key}>{field.label}</option>)}
              </select>
              {selectedField && <small>Ejemplo ficticio: {selectedField.sample}</small>}
            </div>
          )}
          <label><input type="radio" name="completion" checked={mode === 'fixed'} onChange={() => { setMode('fixed'); setError('') }} /> <span><strong>Usar el mismo valor en todas las filas</strong><small>Por ejemplo: proyecto, sede o centro de costo.</small></span></label>
          {mode === 'fixed' && <div className="nested-field form-field"><label htmlFor="fixed-value">Valor fijo</label><input id="fixed-value" value={fixedValue} maxLength={80} onChange={(event) => { setFixedValue(event.target.value); setError('') }} /></div>}
          <label><input type="radio" name="completion" checked={mode === 'blank'} onChange={() => { setMode('blank'); setError('') }} /> <span><strong>Dejarla vacía</strong><small>Se incluirá en el resultado para completarla posteriormente.</small></span></label>
        </fieldset>
        <Button type="button" variant="quiet" disabled>Buscar un dato nuevo en el documento — próximamente</Button>
        <p id={errorId} className="field-error" role={error ? 'alert' : undefined} aria-live={error ? 'assertive' : undefined}>{error}</p>
        <div className="button-row"><Button type="submit">Añadir columna</Button><Button type="button" variant="quiet" onClick={onCancel}>Cancelar</Button></div>
      </form>
    </section>
  )
}
