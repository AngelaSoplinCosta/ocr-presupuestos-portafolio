import { useState } from 'react'
import { DragDropProvider } from '@dnd-kit/react'
import { isSortable, useSortable } from '@dnd-kit/react/sortable'
import type { ColumnDefinition } from '../types'
import { AddColumnPanel } from './AddColumnPanel'
import { Button } from './Button'
import { HelpDisclosure } from './HelpDisclosure'

export function ColumnEditor({ columns, onChange }: { columns: ColumnDefinition[]; onChange: (columns: ColumnDefinition[]) => void }) {
  const [adding, setAdding] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const [dragMessage, setDragMessage] = useState('')
  const update = (index: number, patch: Partial<ColumnDefinition>) => onChange(columns.map((column, position) => position === index ? { ...column, ...patch } : column))
  const move = (index: number, offset: number) => {
    const target = index + offset
    if (target < 0 || target >= columns.length) return
    const next = [...columns]
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next)
    setAnnouncement(`La columna ${columns[index].label} se movió a la posición ${target + 1}`)
  }

  const remove = (index: number) => {
    const column = columns[index]
    if (!column.userCreated) return
    onChange(columns.filter((_, position) => position !== index))
    setAnnouncement(`La columna ${column.label} se eliminó de la configuración`)
  }

  return (
    <div>
      <p className="drag-status" role="status" aria-live="polite">{dragMessage || announcement}</p>
      <DragDropProvider
        onDragStart={(event) => {
          const column = columns.find((item) => item.key === event.operation.source?.id)
          if (column) setDragMessage(`Moviendo la columna ${column.label}. Posición actual ${column.position + 1}`)
        }}
        onDragOver={(event) => {
          const { source } = event.operation
          if (isSortable(source)) {
            const column = columns.find((item) => item.key === source.id)
            if (column) setDragMessage(`Moviendo la columna ${column.label} a la posición ${source.index + 1}`)
          }
        }}
        onDragEnd={(event) => {
          setDragMessage('')
          if (event.canceled) return
          const { source } = event.operation
          if (!isSortable(source) || source.initialIndex === source.index) return
          const next = [...columns]
          const [moved] = next.splice(source.initialIndex, 1)
          next.splice(source.index, 0, moved)
          onChange(next)
          setAnnouncement(`La columna ${moved.label} se movió a la posición ${source.index + 1}`)
        }}
      >
        <div className="column-editor" aria-label="Columnas disponibles">
          {columns.map((column, index) => (
            <SortableColumnRow key={column.key} column={column} index={index} count={columns.length} onUpdate={(patch) => update(index, patch)} onMove={(offset) => move(index, offset)} onRemove={() => remove(index)} />
          ))}
        </div>
      </DragDropProvider>
      {!adding && <div className="add-column-action"><Button type="button" variant="secondary" onClick={() => setAdding(true)}>+ Añadir columna</Button></div>}
      {adding && <AddColumnPanel columns={columns} onCancel={() => setAdding(false)} onAdd={(column) => { onChange([...columns, column]); setAdding(false); setAnnouncement(`La columna ${column.label} se añadió en la posición ${columns.length + 1}`) }} />}
    </div>
  )
}

function SortableColumnRow({ column, index, count, onUpdate, onMove, onRemove }: { column: ColumnDefinition; index: number; count: number; onUpdate: (patch: Partial<ColumnDefinition>) => void; onMove: (offset: number) => void; onRemove: () => void }) {
  const { ref, handleRef, isDragSource, isDropTarget } = useSortable({ id: column.key, index, transition: { duration: 180, idle: true } })
  return (
        <section ref={ref} className={`column-row ${isDragSource ? 'column-row--dragging' : ''} ${isDropTarget ? 'column-row--target' : ''}`} aria-label={`Configurar columna ${column.label}`}>
          <button ref={handleRef} type="button" className="drag-handle" aria-label={`Arrastrar columna ${column.label}`} aria-pressed={isDragSource}>
            <span aria-hidden="true">⠿</span><span>Arrastrar</span>
          </button>
          <label className="check-control">
            <input type="checkbox" checked={column.included} onChange={(event) => onUpdate({ included: event.target.checked })} />
            <span>Incluir</span>
          </label>
          <div className="column-row__name">
            <label htmlFor={`label-${column.key}`}>Título visible</label>
            <input id={`label-${column.key}`} value={column.label} maxLength={60} onChange={(event) => onUpdate({ label: event.target.value })} />
            <small>Clave interna: <code>{column.key}</code> · Origen: {column.origin === 'detected' ? 'información detectada' : column.origin === 'fixed' ? 'valor fijo' : 'columna vacía'} · Posición {index + 1}</small>
          </div>
          <div className="column-row__controls" aria-label={`Orden de ${column.label}`}>
            <Button type="button" variant="quiet" onClick={() => onMove(-1)} disabled={index === 0} aria-label={`Mover ${column.label} arriba`}>↑ Arriba</Button>
            <Button type="button" variant="quiet" onClick={() => onMove(1)} disabled={index === count - 1} aria-label={`Mover ${column.label} abajo`}>↓ Abajo</Button>
            <Button type="button" variant="quiet" onClick={() => onUpdate({ label: column.defaultLabel })} disabled={column.label === column.defaultLabel}>Restaurar nombre</Button>
            {column.userCreated && <Button type="button" variant="quiet" onClick={onRemove} aria-label={`Eliminar columna ${column.label}`}>Eliminar</Button>}
          </div>
          <HelpDisclosure question="Información adicional">{column.detail}</HelpDisclosure>
        </section>
  )
}
