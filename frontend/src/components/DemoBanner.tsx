export function DemoBanner({ compact = false }: { compact?: boolean }) {
  return (
    <aside className={`demo-banner ${compact ? 'demo-banner--compact' : ''}`} aria-label="Aviso de demostración">
      <strong>Datos de ejemplo</strong>
      {!compact && <span> Todo lo mostrado es ficticio y no representa a una empresa real.</span>}
    </aside>
  )
}
