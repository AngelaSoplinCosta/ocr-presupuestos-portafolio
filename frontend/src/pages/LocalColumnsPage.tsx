import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { InlineAlert } from '../components/InlineAlert'
import { PageHeader } from '../components/PageHeader'
import { getLocalExport, saveLocalExportConfig } from '../api/localJobs'
import type { LocalExport } from '../types'

export function LocalColumnsPage() {
  const { jobId = '' } = useParams(); const navigate = useNavigate(); const [state, setState] = useState<LocalExport | null>(null); const [error, setError] = useState('')
  useEffect(() => { getLocalExport(jobId).then(setState).catch(() => setError('No se pudo obtener la configuración de exportación.')) }, [jobId])
  const save = async () => { if (!state) return; try { await saveLocalExportConfig(jobId, state.export_revision, state.columns); navigate(`/documentos/local/${jobId}/resultado`) } catch { setError('La configuración cambió. Actualiza e inténtalo nuevamente.') } }
  const ordered = state?.columns.slice().sort((left, right) => left.position - right.position) ?? []
  const move = (key: string, direction: -1 | 1) => {
    if (!state) return
    const index = ordered.findIndex(item => item.key === key); const other = ordered[index + direction]
    if (!other) return
    setState({ ...state, columns: state.columns.map(item => item.key === key ? { ...item, position: other.position } : item.key === other.key ? { ...item, position: ordered[index].position } : item) })
  }
  return <div className="flow-page"><PageHeader title="Elige columnas para el Excel" description="La configuración se aplicará solo a este resultado local." eyebrow="Paso 4 de 5 · Columnas" />{error && <InlineAlert title="No se pudo guardar" tone="error">{error}</InlineAlert>}{state && <><div className="column-editor">{ordered.map((column, index) => <section key={column.key} className="column-row"><label><input type="checkbox" checked={column.included} onChange={event => setState({ ...state, columns: state.columns.map(item => item.key === column.key ? { ...item, included: event.target.checked } : item) })} /> Incluir</label><div className="column-row__name"><label htmlFor={column.key}>Título visible</label><input id={column.key} value={column.label} maxLength={60} onChange={event => setState({ ...state, columns: state.columns.map(item => item.key === column.key ? { ...item, label: event.target.value } : item) })} /></div><div className="column-row__order"><Button variant="quiet" aria-label={`Subir ${column.label}`} disabled={index === 0} onClick={() => move(column.key, -1)}>↑</Button><Button variant="quiet" aria-label={`Bajar ${column.label}`} disabled={index === ordered.length - 1} onClick={() => move(column.key, 1)}>↓</Button></div></section>)}</div><div className="sticky-actions"><Button onClick={save} disabled={!state.columns.some(item => item.included)}>Continuar al Excel</Button></div></>}</div>
}
