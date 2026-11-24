import { useCallback, useEffect, useMemo, useState } from 'react'
import { getLocalReviewTable, LocalJobError, saveLocalDecisions } from '../api/localJobs'
import { Button } from './Button'
import { InlineAlert } from './InlineAlert'
import { LocalReviewDrawer } from './LocalReviewDrawer'
import { PageHeader } from './PageHeader'
import { humanColumnLabel, humanFieldLabel } from './reviewLabels'
import type { ExportColumn, LocalReviewDecision, LocalReviewRow, LocalReviewTable as ReviewTable, ReviewObservation } from '../types'

type Filter = 'pending' | 'resolved' | 'all'
type Selected = { row: LocalReviewRow; observation: ReviewObservation }
type BatchAction = 'keep_original' | 'accept_suggestion'

const batchActions: BatchAction[] = ['keep_original', 'accept_suggestion']

function safeError(error: unknown) {
  return error instanceof LocalJobError ? error.message : 'No pudimos guardar la decisión.'
}

function displayNumeric(value: string, column: ExportColumn) {
  if (column.data_type === 'text' || !/^-?\d+(?:[.,]\d{1,2})?$/.test(value)) return value || '—'
  const normalized = Number(value.replace(',', '.'))
  if (!Number.isFinite(normalized)) return value
  const decimals = value.includes('.') || value.includes(',') ? value.length - Math.max(value.lastIndexOf('.'), value.lastIndexOf(',')) - 1 : 0
  return new Intl.NumberFormat('es-PE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(normalized)
}

export function LocalReviewTable({ columns, rows, onSelect, selectedIds, onToggle }: {
  columns: ExportColumn[]
  rows: LocalReviewRow[]
  onSelect: (row: LocalReviewRow, observation: ReviewObservation) => void
  selectedIds: Set<string>
  onToggle: (observation: ReviewObservation) => void
}) {
  const visible = columns.filter(column => column.included).sort((a, b) => a.position - b.position)
  return <div className="local-review-table"><table><thead><tr>{visible.map(column => <th key={column.key} data-mobile={column.key === 'item' || column.key === 'description' ? 'visible' : 'hidden'}>{humanColumnLabel(column)}</th>)}<th data-mobile="visible">Estado</th></tr></thead><tbody>{rows.map(row => {
    const structured = row.structured_review
    const rowObservation = row.observations.find(item => item.target?.scope === 'row')
    const pending = structured ? structured.pending_field_count > 0 : row.observations.some(item => item.state === 'PENDING')
    const status = structured ? `${structured.confirmed_field_count} de 6 campos confirmados` : pending ? 'Pendiente' : row.observations.length ? 'Resuelta' : 'Sin observaciones'
    return <tr key={row.row_key} className={rowObservation ? 'review-row--observed' : ''}>{visible.map((column, index) => {
      const observation = row.observations.find(item => item.target?.scope === 'cell' && item.target.column_key === column.key)
      const cellObservation = observation ?? (index === 0 ? rowObservation : undefined)
      const selected = cellObservation ? selectedIds.has(cellObservation.id) : false
      const allowSelection = !structured
      return <td key={column.key} data-mobile={column.key === 'item' || column.key === 'description' ? 'visible' : 'hidden'} className={observation ? `review-cell--${observation.state.toLowerCase()}` : ''} onClick={() => cellObservation && onSelect(row, cellObservation)}><span className={column.data_type === 'text' ? '' : 'numeric-value'}>{displayNumeric(row.cells[column.key], column)}</span>{allowSelection && cellObservation?.state === 'PENDING' && <label className="review-select" onClick={event => event.stopPropagation()}><input type="checkbox" checked={selected} onChange={() => onToggle(cellObservation)} aria-label={`Seleccionar ${humanFieldLabel(cellObservation.field)} de la fila ${row.order ?? ''}`} /> Seleccionar</label>}{allowSelection && index === 0 && rowObservation && rowObservation !== cellObservation && rowObservation.state === 'PENDING' && <label className="review-select" onClick={event => event.stopPropagation()}><input type="checkbox" checked={selectedIds.has(rowObservation.id)} onChange={() => onToggle(rowObservation)} aria-label={`Seleccionar revisión de fila ${row.order ?? ''}`} /> Seleccionar fila</label>}{index === 0 && rowObservation && <button className="review-row-action" onClick={(event) => { event.stopPropagation(); onSelect(row, rowObservation) }}>{structured ? 'Revisar fila estructurada' : 'Revisar fila'}</button>}</td>
    })}<td data-mobile="visible" className={`review-status review-status--${pending ? 'pending' : 'resolved'}`}>{status}</td></tr>
  })}</tbody></table></div>
}

export function LocalTabularReviewPage({ jobId }: { jobId: string }) {
  const [table, setTable] = useState<ReviewTable | null>(null)
  const [filter, setFilter] = useState<Filter>('pending')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Selected | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [pendingBatchAction, setPendingBatchAction] = useState<BatchAction | null>(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  const refresh = useCallback(() => getLocalReviewTable(jobId, offset, filter).then(next => {
    setTable(next)
    setSelected(current => {
      if (!current) return null
      const row = next.rows.find(item => item.row_key === current.row.row_key)
      const observation = row?.observations.find(item => item.id === current.observation.id)
      return row && observation ? { row, observation } : null
    })
    const pendingIds = new Set(next.rows.flatMap(row => row.observations).filter(item => item.state === 'PENDING').map(item => item.id))
    setSelectedIds(current => new Set([...current].filter(id => pendingIds.has(id))))
  }).catch(requestError => setError(safeError(requestError))), [filter, jobId, offset])

  useEffect(() => { void refresh() }, [refresh])

  const selectedObservations = useMemo(() => {
    if (!table) return []
    return table.rows.flatMap(row => row.structured_review ? [] : row.observations).filter(item => item.state === 'PENDING' && selectedIds.has(item.id))
  }, [selectedIds, table])
  const selectedScope = selectedObservations[0]?.target?.scope
  const sameScope = (selectedScope === 'cell' || selectedScope === 'row') && selectedObservations.every(item => item.target?.scope === selectedScope)
  const hasCompatibleSelection = selectedObservations.length > 0 && sameScope && selectedObservations.length <= 50
  const compatibleActions = hasCompatibleSelection
    ? batchActions.filter(action => selectedObservations.every(item => item.allowed_actions.includes(action)))
    : []
  const canBatch = compatibleActions.length > 0

  const save = (decision: LocalReviewDecision) => {
    if (!table || !selected) return
    setError(''); setSaved(''); setPendingBatchAction(null)
    void saveLocalDecisions(jobId, table.review_revision, [decision])
      .then(() => {
        setSaved(decision.action === 'confirm_provisional_row' ? 'Provisional confirmado' : 'Decisión guardada')
        return refresh()
      })
      .catch(requestError => { if (requestError instanceof LocalJobError && requestError.code === 'STALE_REVIEW_REVISION') void refresh(); setError(safeError(requestError)) })
  }

  const saveBatch = () => {
    if (!table || !pendingBatchAction || !canBatch) return
    const decisions = selectedObservations.map(item => ({ observation_id: item.id, action: pendingBatchAction }))
    setError(''); setSaved('')
    void saveLocalDecisions(jobId, table.review_revision, decisions)
      .then(() => {
        const count = decisions.length
        setSelected(current => current && selectedIds.has(current.observation.id) ? { ...current, observation: { ...current.observation, state: 'RESOLVED' } } : current)
        setSelectedIds(new Set<string>())
        setPendingBatchAction(null)
        setSaved(`Se aplicaron ${count} decisiones`)
        return refresh()
      })
      .catch(requestError => { if (requestError instanceof LocalJobError && requestError.code === 'STALE_REVIEW_REVISION') void refresh(); setError(safeError(requestError)) })
  }

  const toggle = (observation: ReviewObservation) => {
    setSelectedIds(current => {
      const next = new Set(current)
      if (next.has(observation.id)) next.delete(observation.id)
      else if (next.size < 50) next.add(observation.id)
      return next
    })
    setPendingBatchAction(null)
  }
  const changeFilter = (next: Filter) => { setOffset(0); setFilter(next); setSelectedIds(new Set<string>()); setPendingBatchAction(null) }
  const batchLabel = pendingBatchAction === 'keep_original' ? 'mantener los valores detectados' : 'aceptar las sugerencias'

  if (!table && !error) return <div className="flow-page"><p>Cargando revisión…</p></div>
  return <div className="flow-page review-page"><PageHeader title="Revisión guiada" description="Compara los valores detectados y sugeridos; ninguna decisión se aplica automáticamente." eyebrow="Paso 3 de 4" />{error && <InlineAlert title="No se pudo actualizar la revisión" tone="error">{error}</InlineAlert>}<div className="review-toolbar"><strong>{table?.pending_decision_count ?? 0} pendientes</strong><div className="segmented" aria-label="Filtrar observaciones"><Button variant={filter === 'pending' ? 'primary' : 'quiet'} onClick={() => changeFilter('pending')}>Pendientes</Button><Button variant={filter === 'resolved' ? 'primary' : 'quiet'} onClick={() => changeFilter('resolved')}>Resueltas</Button><Button variant={filter === 'all' ? 'primary' : 'quiet'} onClick={() => changeFilter('all')}>Todas</Button></div></div>{saved && <InlineAlert title={saved} tone="success">La tabla fue actualizada.</InlineAlert>}{table && <><section className="review-batch" aria-label="Decisiones por lote"><strong>{selectedObservations.length} seleccionadas</strong>{selectedObservations.length > 0 && !canBatch && <span>Selecciona observaciones pendientes del mismo alcance y con una acción común.</span>}{canBatch && !pendingBatchAction && compatibleActions.map(action => <Button key={action} variant="secondary" onClick={() => setPendingBatchAction(action)}>Aplicar por lote: {action === 'keep_original' ? 'mantener detectados' : 'aceptar sugerencias'}</Button>)}{pendingBatchAction && <div><p>Se aplicarán {selectedObservations.length} decisiones para {batchLabel}. Los valores se conservan individualmente.</p><Button onClick={saveBatch}>Confirmar lote</Button><Button variant="quiet" onClick={() => setPendingBatchAction(null)}>Cancelar</Button></div>}</section><div className="review-table-workspace"><section>{table.rows.length ? <LocalReviewTable columns={table.columns} rows={table.rows} selectedIds={selectedIds} onToggle={toggle} onSelect={(row, observation) => { setSelected({ row, observation }); setSaved('') }} /> : <InlineAlert title="No hay filas en este filtro" tone="success">Cambia el filtro para ver otras decisiones.</InlineAlert>}{table.total_count > table.limit && <div className="pager"><Button variant="quiet" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - table.limit))}>← Anterior</Button><span>{offset + 1}–{Math.min(offset + table.limit, table.total_count)} de {table.total_count}</span><Button variant="quiet" disabled={offset + table.limit >= table.total_count} onClick={() => setOffset(offset + table.limit)}>Siguiente →</Button></div>}</section><LocalReviewDrawer jobId={jobId} observation={selected?.observation ?? null} row={selected?.row ?? null} onSave={save} /></div></>}<div className="sticky-actions review-footer"><Button onClick={() => { window.location.assign(`/documentos/local/${jobId}/columnas`) }} disabled={(table?.pending_decision_count ?? 1) > 0}>Continuar a columnas</Button></div></div>
}
