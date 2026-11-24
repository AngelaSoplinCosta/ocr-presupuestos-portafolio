import type { ReactNode } from 'react'

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="empty-state" aria-labelledby="empty-state-title">
      <div className="empty-state__icon" aria-hidden="true">□</div>
      <h2 id="empty-state-title">{title}</h2>
      <div>{children}</div>
      {action && <div className="empty-state__action">{action}</div>}
    </section>
  )
}
