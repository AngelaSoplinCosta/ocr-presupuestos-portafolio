import type { ReactNode } from 'react'

export function InlineAlert({ title, children, tone = 'info' }: { title: string; children: ReactNode; tone?: 'info' | 'warning' | 'error' | 'success' }) {
  return (
    <div className={`inline-alert inline-alert--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <strong>{title}</strong>
      <div>{children}</div>
    </div>
  )
}
