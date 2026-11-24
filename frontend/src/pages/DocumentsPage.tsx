import { useMemo, useState } from 'react'
import { Button } from '../components/Button'
import { DemoBanner } from '../components/DemoBanner'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { demoDocuments } from '../data/demoData'
import type { DocumentStatus } from '../types'

export function DocumentsPage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'Todos' | DocumentStatus>('Todos')
  const [showExamples, setShowExamples] = useState(true)
  const results = useMemo(() => showExamples ? demoDocuments.filter((doc) => doc.name.toLowerCase().includes(query.toLowerCase()) && (status === 'Todos' || doc.status === status)) : [], [query, status, showExamples])

  return (
    <div className="page-container">
      <DemoBanner />
      <PageHeader title="Documentos" description="Consulta estados y resultados ficticios sin perder la información esencial en pantallas pequeñas." actions={<Button variant="secondary" onClick={() => setShowExamples((value) => !value)}>{showExamples ? 'Ocultar ejemplos' : 'Mostrar ejemplos'}</Button>} />
      <div className="filters"><div className="form-field"><label htmlFor="search-documents">Buscar por nombre</label><input id="search-documents" type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></div><div className="form-field"><label htmlFor="filter-status">Filtrar por estado</label><select id="filter-status" value={status} onChange={(event) => setStatus(event.target.value as 'Todos' | DocumentStatus)}><option>Todos</option>{['Recibido','Listo','Necesita revisión','Procesando','No se pudo procesar'].map((value) => <option key={value}>{value}</option>)}</select></div></div>
      {results.length === 0 ? (
        <EmptyState title={showExamples ? 'No hay resultados para esta búsqueda' : 'Aún no hay documentos'}><p>{showExamples ? 'Prueba con otro nombre o estado. Los filtros pueden modificarse sin perder información.' : 'Cuando inicies una demostración, aquí podrás reconocer el historial ficticio.'}</p></EmptyState>
      ) : (
        <>
          <div className="table-wrap"><table><caption className="sr-only">Historial de documentos de ejemplo</caption><thead><tr><th scope="col">Documento</th><th scope="col">Tipo</th><th scope="col">Fecha</th><th scope="col">Registros</th><th scope="col">Estado</th><th scope="col">Acción</th></tr></thead><tbody>{results.map((doc) => <tr key={doc.id}><th scope="row">{doc.name}<small>Datos de ejemplo</small></th><td>{doc.type}</td><td>{doc.date}</td><td>{doc.records ?? 'No disponible'}</td><td><StatusBadge status={doc.status} /></td><td><Button variant="quiet">Consultar</Button></td></tr>)}</tbody></table></div>
          <ul className="document-cards" aria-label="Historial de documentos de ejemplo">{results.map((doc) => <li key={doc.id}><strong>{doc.name}</strong><span className="example-label">Datos de ejemplo</span><dl><div><dt>Tipo</dt><dd>{doc.type}</dd></div><div><dt>Fecha</dt><dd>{doc.date}</dd></div><div><dt>Registros</dt><dd>{doc.records ?? 'No disponible'}</dd></div></dl><StatusBadge status={doc.status} /><Button variant="quiet">Consultar documento</Button></li>)}</ul>
        </>
      )}
      <section className="status-help" aria-labelledby="status-help-title"><h2 id="status-help-title">Cómo interpretar los estados</h2><dl><div><dt><StatusBadge status="Recibido" /></dt><dd>La solicitud fue admitida y espera el procesamiento.</dd></div><div><dt><StatusBadge status="Necesita revisión" /></dt><dd>El documento fue procesado, pero algunos datos necesitan validación humana.</dd></div><div><dt><StatusBadge status="No se pudo procesar" /></dt><dd>El sistema confirmó que no pudo terminar.</dd></div></dl></section>
    </div>
  )
}
