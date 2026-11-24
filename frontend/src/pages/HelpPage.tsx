import { HelpDisclosure } from '../components/HelpDisclosure'
import { PageHeader } from '../components/PageHeader'

export function HelpPage() {
  return (
    <div className="page-container narrow-page">
      <PageHeader title="Ayuda" description="Qué ocurre al cargar, revisar y exportar un presupuesto." />
      <section className="help-list" aria-label="Temas de ayuda">
        <HelpDisclosure question="¿Qué documentos admite el piloto?">Presupuestos en PDF de hasta 50 MB. El resultado depende del formato del documento; comprueba las partidas y los importes antes de usar el Excel.</HelpDisclosure>
        <HelpDisclosure question="¿Cómo funciona la selección de columnas?">Puedes incluir o excluir columnas, cambiar su título y ordenarlas. En el recorrido local, la configuración de la exportación se guarda con ese trabajo hasta su vencimiento.</HelpDisclosure>
        <HelpDisclosure question="¿Qué significan los estados?">“Recibido” confirma la admisión. “Procesando” indica trabajo en curso. “Listo” es un resultado completado. “Necesita revisión” pide una decisión humana. “No se pudo procesar” es un resultado confirmado.</HelpDisclosure>
        <HelpDisclosure question="¿Revisión documental y verificación técnica son lo mismo?">No. La revisión documental compara datos visibles; la verificación técnica indica que todavía falta confirmar si el proceso pudo completarse.</HelpDisclosure>
        <HelpDisclosure question="¿Puedo conservar el valor detectado?">Sí. La sugerencia nunca se presenta como verdad ni se aplica silenciosamente. Quien revisa mantiene el control.</HelpDisclosure>
        <HelpDisclosure question="¿Qué ocurre con mi archivo?">Al continuar, el navegador lo envía a la API local en tu equipo. El PDF se conserva temporalmente en el directorio privado del trabajo para compararlo durante la revisión y se elimina con la limpieza de resultados vencidos. Recargar la página no borra esa copia.</HelpDisclosure>
        <HelpDisclosure question="¿Los datos de ejemplo son reales?">No. El recorrido de ejemplo y el historial ilustrativo usan datos inventados y no generan un Excel. Para procesar un presupuesto, sube tu propio PDF.</HelpDisclosure>
      </section>
    </div>
  )
}
