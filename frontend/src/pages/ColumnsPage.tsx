import { Navigate, useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { ColumnEditor } from '../components/ColumnEditor'
import { DemoBanner } from '../components/DemoBanner'
import { PageHeader } from '../components/PageHeader'
import { Toast } from '../components/Toast'
import { initialColumns } from '../data/demoData'
import { useApp } from '../hooks/useApp'

export function ColumnsPage() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  if (!state.file && !state.demo) return <Navigate to="/documentos/nuevo" replace />
  if (!state.processingComplete) return <Navigate to="/documentos/nuevo/procesamiento" replace />

  const continueToReview = () => {
    dispatch({ type: 'CONFIRM_COLUMNS' })
    navigate('/documentos/demo/revision')
  }

  return (
    <div className="flow-page">
      {state.demo && <DemoBanner />}
      <PageHeader title="Elige y organiza las columnas" description="Hemos analizado el documento y detectado la información disponible. Selecciona qué columnas quieres incluir, cambia sus nombres, arrástralas para ordenar su posición o añade una nueva." eyebrow="Paso 3 de 5" />
      <p className="detected-data-note">Los datos mostrados son ficticios y se utilizan únicamente para demostrar el funcionamiento.</p>
      <ColumnEditor columns={state.columns} onChange={(columns) => dispatch({ type: 'SET_COLUMNS', columns })} />
      {state.templateMessage && <Toast message={state.templateMessage} />}
      <div className="sticky-actions" aria-label="Acciones de configuración">
        <div className="sticky-actions__secondary">
          <Button variant="quiet" onClick={() => dispatch({ type: 'SET_COLUMNS', columns: initialColumns.map((column) => ({ ...column })) })}>Restaurar configuración</Button>
          <Button variant="secondary" onClick={() => dispatch({ type: 'SAVE_TEMPLATE_DEMO' })}>Guardar como plantilla</Button>
        </div>
        <Button onClick={continueToReview} disabled={!state.columns.some((column) => column.included)}>Continuar a revisión</Button>
      </div>
    </div>
  )
}
