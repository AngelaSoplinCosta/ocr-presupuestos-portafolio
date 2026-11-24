export interface ProcessStep {
  label: string
  mobileLabel: string
}

const defaultSteps: ProcessStep[] = [
  { label: 'Documento', mobileLabel: 'PDF' },
  { label: 'Procesamiento', mobileLabel: 'Datos' },
  { label: 'Columnas', mobileLabel: 'Columnas' },
  { label: 'Revisión', mobileLabel: 'Revisar' },
  { label: 'Resultado', mobileLabel: 'Excel' },
]

export function StepIndicator({ current, steps = defaultSteps }: { current: number; steps?: ProcessStep[] }) {
  return (
    <nav className="step-indicator" aria-label="Progreso del proceso">
      <ol style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((step, index) => {
          const number = index + 1
          const state = number < current ? 'completed' : number === current ? 'current' : 'upcoming'
          return (
            <li key={step.label} className={`step step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="step__number" aria-hidden="true">{state === 'completed' ? '✓' : number}</span>
              <span className="step__label">
                <span className="sr-only">Paso {number}: {step.label}, {state === 'completed' ? 'completado' : state === 'current' ? 'actual' : 'pendiente'}.</span>
                <span className="step__label-full" aria-hidden="true">{step.label}</span>
                <span className="step__label-mobile" aria-hidden="true">{step.mobileLabel}</span>
              </span>
              <span className="step__connector" aria-hidden="true" />
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
