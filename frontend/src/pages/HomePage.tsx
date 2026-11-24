import { useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { useApp } from '../hooks/useApp'

export function HomePage() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  const startExample = () => { dispatch({ type: 'START_DEMO' }); navigate('/documentos/nuevo/procesamiento') }
  const showHowItWorks = () => {
    const flow = document.getElementById('home-flow')
    flow?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    flow?.focus({ preventScroll: true })
  }

  return (
    <div className="page-container home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero__copy">
          <p className="home-kicker"><span className="home-kicker__node" aria-hidden="true" />Extracción documental con revisión humana</p>
          <h1 id="home-title" data-page-title tabIndex={-1}>De presupuesto en PDF a Excel confiable</h1>
          <p className="home-hero__description">Carga un documento escaneado o digital. Quipta extrae la información, te muestra la evidencia y te permite organizar las columnas antes de preparar tu Excel.</p>
          <div className="home-hero__actions">
            <Button onClick={() => navigate('/documentos/nuevo')}>Subir presupuesto en PDF</Button>
            <Button variant="secondary" onClick={showHowItWorks}>Ver cómo funciona</Button>
          </div>
          <div className="home-result" aria-label="Resultado esperado: Excel">
            <span className="home-result__node" aria-hidden="true">✓</span>
            <span>Resultado: Excel (.xlsx)</span>
          </div>
          <ul className="home-trust" aria-label="Condiciones del piloto">
            <li><span aria-hidden="true">●</span>Procesamiento local durante el piloto</li>
            <li><span aria-hidden="true">●</span>Tú confirmas los datos dudosos</li>
            <li><span aria-hidden="true">●</span>Archivo de hasta 50 MB</li>
          </ul>
          <details className="home-help">
            <summary>¿Qué significa procesamiento local?</summary>
            <p>Durante este piloto, el documento se procesa en tu equipo y no se envía a servicios externos.</p>
          </details>
        </div>

        <div className="home-demo" aria-label="Demostración visual de PDF a datos organizados">
          <div className="home-demo__heading"><h2>De PDF a datos organizados</h2><span>Vista previa</span></div>
          <div className="home-demo__document">
            <div className="home-document" aria-hidden="true"><span className="home-document__fold" /><span /><span className="short" /><span className="medium" /><strong>03&nbsp;&nbsp; Trabajo general</strong><span className="short" /></div>
            <div className="home-demo__metadata"><strong>Presupuesto de obra</strong><span>48 partidas detectadas</span><span>PDF local · página 4</span></div>
          </div>
          <div className="home-demo__checks" aria-label="Datos que se pueden verificar">
            <div><span aria-hidden="true">✓</span><strong>Partidas detectadas</strong><span>48 registros</span></div>
            <div><span aria-hidden="true">!</span><strong>Observaciones</strong><span>2 para revisar</span></div>
            <div><span aria-hidden="true">□</span><strong>Columnas</strong><span>Organizadas por ti</span></div>
          </div>
          <Button type="button" variant="quiet" onClick={startExample}>Probar con un documento de ejemplo</Button>
        </div>
      </section>

      <section className="home-flow" id="home-flow" tabIndex={-1} aria-labelledby="home-flow-title">
        <div className="home-flow__heading"><h2 id="home-flow-title">Tu recorrido en Quipta</h2><span>Sin pasos ocultos</span></div>
        <ol className="home-steps" aria-label="PDF, extracción, revisión, columnas y Excel">
          {['PDF', 'Extracción', 'Revisión', 'Columnas', 'Excel'].map((step, index) => (
            <li key={step} className={index === 4 ? 'home-step home-step--result' : 'home-step'}>
              <span className="home-step__node" aria-hidden="true">{index === 4 ? '✓' : index + 1}</span><span>{step}</span>
              {index < 4 && <span className="home-step__connector" aria-hidden="true" />}
            </li>
          ))}
        </ol>
      </section>

      {state.demo || state.file ? <p className="home-process-note">El proceso actual continúa en tu espacio de trabajo.</p> : null}
    </div>
  )
}
