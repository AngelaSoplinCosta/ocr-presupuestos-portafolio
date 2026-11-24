import { NavLink, Outlet } from 'react-router-dom'

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Saltar al contenido</a>
      <header className="site-header">
        <NavLink to="/" className="brand" aria-label="Quipta, inicio">
          <span className="brand__mark" aria-hidden="true">Q</span>
          <span>Quipta</span>
          <span className="brand__scope">Piloto local</span>
          <span className="brand__node" aria-hidden="true" />
        </NavLink>
        <nav aria-label="Navegación principal">
          <NavLink to="/" end>Inicio</NavLink>
          <NavLink to="/documentos">Documentos</NavLink>
          <NavLink to="/plantillas">Plantillas</NavLink>
          <NavLink to="/ayuda">Ayuda</NavLink>
        </nav>
      </header>
      <main id="main-content" className="main-content"><Outlet /></main>
      <footer className="site-footer" />
    </div>
  )
}
