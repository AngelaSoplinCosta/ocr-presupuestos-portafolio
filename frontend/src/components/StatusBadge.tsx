import type { DocumentStatus } from '../types'

const statusDetails: Record<DocumentStatus, { icon: string; className: string }> = {
  'Recibido': { icon: '○', className: 'status--pending' },
  'Listo': { icon: '✓', className: 'status--ready' },
  'Necesita revisión': { icon: '!', className: 'status--review' },
  'Procesando': { icon: '…', className: 'status--processing' },
  'No se pudo procesar': { icon: '×', className: 'status--error' },
}

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const details = statusDetails[status]
  return (
    <span className={`status-badge ${details.className}`}>
      <span aria-hidden="true">{details.icon}</span>
      {status}
    </span>
  )
}
