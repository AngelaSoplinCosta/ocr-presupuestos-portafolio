import { useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'

export function NotFoundPage() {
  const navigate = useNavigate()
  return <div className="page-container narrow-page"><PageHeader title="Página no encontrada" description="La dirección no corresponde a una pantalla disponible." /><EmptyState title="No pudimos abrir esta página" action={<Button onClick={() => navigate('/')}>Volver al inicio</Button>}><p>Puedes regresar al inicio sin perder información de esta sesión.</p></EmptyState></div>
}
