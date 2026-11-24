import type { ReactNode } from 'react'

export function HelpDisclosure({ question, children }: { question: string; children: ReactNode }) {
  return (
    <details className="help-disclosure">
      <summary>{question}</summary>
      <div>{children}</div>
    </details>
  )
}
