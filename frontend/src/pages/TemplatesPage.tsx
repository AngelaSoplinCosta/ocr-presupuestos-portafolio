import { useState } from 'react'
import { Button } from '../components/Button'
import { InlineAlert } from '../components/InlineAlert'
import { PageHeader } from '../components/PageHeader'
import { Toast } from '../components/Toast'
import { initialColumns } from '../data/demoData'
import { useApp } from '../hooks/useApp'

export function TemplatesPage() {
  const { state, dispatch } = useApp()
  const [expanded, setExpanded] = useState(false)
  const [duplicating, setDuplicating] = useState(false)
  const [name, setName] = useState('Copia de Presupuesto de obra')
  const [message, setMessage] = useState('')

  const duplicate = () => {
    if (!name.trim()) { setMessage('Escribe un nombre para la copia ficticia.'); return }
    dispatch({ type: 'DUPLICATE_TEMPLATE', name: name.trim() })
    setDuplicating(false)
    setMessage('Plantilla duplicada sólo en memoria para esta demostración')
  }

  return (
    <div className="page-container narrow-page">
      <PageHeader title="Plantillas" description="Consulta configuraciones ficticias de columnas y crea copias temporales." />
      <InlineAlert title="Almacenamiento temporal" tone="warning">Las plantillas de este prototipo no se almacenan. Desaparecen al recargar.</InlineAlert>
      <section className="template-item" aria-labelledby="template-name"><div><p className="eyebrow">Plantilla ficticia</p><h2 id="template-name">Presupuesto de obra</h2><p>{initialColumns.length} columnas configuradas</p></div><div className="button-row"><Button variant="secondary" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>{expanded ? 'Ocultar columnas' : 'Ver columnas'}</Button><Button onClick={() => setDuplicating(true)}>Duplicar en memoria</Button></div></section>
      {expanded && <section className="template-columns" aria-labelledby="template-columns-title"><h2 id="template-columns-title">Columnas incluidas</h2><ol>{initialColumns.map((column) => <li key={column.key}><strong>{column.defaultLabel}</strong><span>{column.detail}</span></li>)}</ol></section>}
      {duplicating && <section className="inline-form" aria-labelledby="duplicate-title"><h2 id="duplicate-title">Crear copia ficticia</h2><label htmlFor="template-copy-name">Nombre de la copia</label><input id="template-copy-name" value={name} onChange={(event) => setName(event.target.value)} /><div className="button-row"><Button onClick={duplicate}>Crear copia</Button><Button variant="quiet" onClick={() => setDuplicating(false)}>Cancelar</Button></div></section>}
      {message && <Toast message={message} />}
      {state.duplicatedTemplates.length > 0 && <section aria-labelledby="copies-title"><h2 id="copies-title">Copias de esta sesión</h2><ul className="simple-list">{state.duplicatedTemplates.map((item, index) => <li key={`${item}-${index}`}>{item}<span>En memoria</span></li>)}</ul></section>}
    </div>
  )
}
