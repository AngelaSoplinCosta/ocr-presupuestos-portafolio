import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useApp } from '../hooks/useApp'
import { Button } from './Button'
import { StepIndicator } from './StepIndicator'

const routeSteps: Record<string, number> = {
  '/documentos/nuevo': 1,
  '/documentos/nuevo/procesamiento': 2,
  '/documentos/nuevo/columnas': 3,
  '/documentos/demo/revision': 4,
  '/documentos/demo/resultado': 5,
}

const localSteps = [
  { label: 'Documento', mobileLabel: 'PDF' },
  { label: 'Procesamiento', mobileLabel: 'Proceso' },
  { label: 'Revisión', mobileLabel: 'Revisión' },
  { label: 'Columnas', mobileLabel: 'Columnas' },
  { label: 'Excel', mobileLabel: 'Excel' },
]

const previousRoutes: Record<number, string> = {
  2: '/documentos/nuevo',
  3: '/documentos/nuevo/procesamiento',
  4: '/documentos/nuevo/columnas',
  5: '/documentos/demo/revision',
}

export function ProcessLayout() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const isLocalResult = location.pathname.startsWith('/documentos/local/')
  const isLocalFlow = !state.demo
  const current = isLocalResult ? (location.pathname.endsWith('/revision') ? 3 : location.pathname.endsWith('/columnas') ? 4 : 5) : routeSteps[location.pathname] ?? 1

  const leave = () => {
    const hasWork = Boolean(state.file || state.demo || Object.keys(state.decisions).length)
    if (hasWork && !window.confirm('Se perderán las decisiones de esta demostración. ¿Quieres salir del proceso?')) return
    dispatch({ type: 'RESET_PROCESS' })
    navigate('/')
  }

  return (
    <div className="process-shell">
      <a className="skip-link" href="#process-content">Saltar al contenido</a>
      <header className="process-header">
        <div className="brand"><span className="brand__mark" aria-hidden="true">Q</span><span>Quipta</span><span className="brand__scope">Piloto local</span><span className="brand__node" aria-hidden="true" /></div>
        <Button type="button" variant="quiet" onClick={leave}>Salir del proceso</Button>
      </header>
      <StepIndicator current={current} steps={isLocalFlow ? localSteps : undefined} />
      <main id="process-content" className="process-content">
        {current > 1 && <Button type="button" variant="quiet" className="back-button" onClick={() => navigate(isLocalResult ? '/documentos/nuevo/procesamiento' : previousRoutes[current])}>← Volver</Button>}
        <Outlet />
      </main>
    </div>
  )
}
