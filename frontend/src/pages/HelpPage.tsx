import { HelpDisclosure } from '../components/HelpDisclosure'
import { PageHeader } from '../components/PageHeader'

export function HelpPage() {
  return (
    <div className="page-container narrow-page">
      <PageHeader title="Ayuda" description="Respuestas breves para completar el recorrido con claridad y control." />
      <section className="help-list" aria-label="Temas de ayuda">
        <HelpDisclosure question="¿Qué documentos admite el prototipo?">La selección local admite PDF de hasta 50 MB. En esta fase el contenido no se lee, envía ni almacena.</HelpDisclosure>
        <HelpDisclosure question="¿Cómo funciona la selección de columnas?">Puedes incluir o excluir columnas, cambiar su título y moverlas con botones. Todo permanece sólo en memoria.</HelpDisclosure>
        <HelpDisclosure question="¿Qué significan los estados?">“Recibido” confirma la admisión. “Procesando” indica trabajo en curso. “Listo” es un resultado completado. “Necesita revisión” pide una decisión humana. “No se pudo procesar” es un resultado confirmado.</HelpDisclosure>
        <HelpDisclosure question="¿Revisión documental y verificación técnica son lo mismo?">No. La revisión documental compara datos visibles; la verificación técnica indica que todavía falta confirmar si el proceso pudo completarse.</HelpDisclosure>
        <HelpDisclosure question="¿Puedo conservar el valor detectado?">Sí. La sugerencia nunca se presenta como verdad ni se aplica silenciosamente. Quien revisa mantiene el control.</HelpDisclosure>
        <HelpDisclosure question="¿Qué ocurre con mi archivo?">Permanece únicamente como objeto en memoria del navegador, no se lee y desaparece al recargar. No se realizan solicitudes de red.</HelpDisclosure>
        <HelpDisclosure question="¿Los datos mostrados son reales?">No. Nombres, montos, estados y resultados son completamente ficticios y están marcados como datos de ejemplo.</HelpDisclosure>
      </section>
    </div>
  )
}
