import type { ColumnDefinition, DemoDocument, DetectedField, Observation } from '../types'

export const detectedFields: DetectedField[] = [
  { key: 'item', label: 'Item', sample: '01', detail: 'Número de orden dentro del documento.' },
  { key: 'description', label: 'Descripción', sample: 'Actividad general ficticia', detail: 'Texto que describe el concepto.' },
  { key: 'unit', label: 'Unidad', sample: 'm2', detail: 'Unidad indicada para la cantidad.' },
  { key: 'quantity', label: 'Metrado', sample: '12.00', detail: 'Cantidad declarada en el documento.' },
  { key: 'unit_price', label: 'Precio unitario', sample: 'S/ 30.00', detail: 'Importe por unidad.' },
  { key: 'subtotal', label: 'Parcial', sample: 'S/ 360.00', detail: 'Importe parcial de la fila.' },
  { key: 'source_page', label: 'Página de origen', sample: '4', detail: 'Página donde se encontró la información.' },
  { key: 'category', label: 'Categoría detectada', sample: 'Trabajos generales', detail: 'Agrupación ficticia identificada en la estructura.' },
  { key: 'reference_code', label: 'Código de referencia', sample: 'REF-01', detail: 'Código ficticio encontrado junto al concepto.' },
]

export const initialColumns: ColumnDefinition[] = [
  ...detectedFields.slice(0, 7).map((field, position) => ({ key: field.key, defaultLabel: field.label, label: field.label, included: true, detail: field.detail, origin: 'detected' as const, position, userCreated: false, linkedField: field.key })),
]

export const observations: Observation[] = [
  {
    id: 'obs-1',
    field: 'Parcial',
    page: 4,
    context: 'Partida 03 — Trabajo general de ejemplo',
    detected: 'S/ 1,177.59',
    suggested: 'S/ 1,177.69',
    reason: 'Posible confusión entre caracteres',
    confidence: 'Media',
    evidence: '03  Trabajo general de ejemplo     und     3.00     392.56     1,177.59',
    linkedField: 'subtotal',
    critical: false,
  },
  {
    id: 'obs-2',
    field: 'Metrado',
    page: 7,
    context: 'Partida 08 — Suministro ficticio',
    detected: '18.00',
    suggested: '16.00',
    reason: 'La cifra se ve distinta en dos secciones',
    confidence: 'Baja',
    evidence: '08  Suministro ficticio             m2      18.00     45.00      720.00',
    linkedField: 'quantity',
    critical: false,
  },
  {
    id: 'obs-3',
    field: 'Unidad',
    page: 9,
    context: 'Partida 11 — Actividad demostrativa',
    detected: 'm',
    suggested: 'm2',
    reason: 'El carácter final no se distingue con claridad',
    confidence: 'Media',
    evidence: '11  Actividad demostrativa          m?      12.00     30.00      360.00',
    linkedField: 'unit',
    critical: false,
  },
  {
    id: 'obs-critical',
    field: 'Conciliación general',
    page: 12,
    context: 'Resumen general del documento ficticio',
    detected: 'S/ 8,420.00',
    suggested: 'Revisar suma final',
    reason: 'El total general no coincide con la suma de los parciales',
    confidence: 'Baja',
    evidence: 'TOTAL GENERAL DE EJEMPLO                         S/ 8,420.00',
    critical: true,
  },
]

export const demoRows: Record<string, string>[] = [
  { item: '01', description: 'Actividad general ficticia', unit: 'm2', quantity: '12.00', unit_price: 'S/ 30.00', subtotal: 'S/ 360.00', source_page: '4', category: 'Trabajos generales', reference_code: 'REF-01' },
  { item: '02', description: 'Suministro demostrativo', unit: 'und', quantity: '3.00', unit_price: 'S/ 45.00', subtotal: 'S/ 135.00', source_page: '7', category: 'Suministros', reference_code: 'REF-02' },
]

export const demoDocuments: DemoDocument[] = [
  { id: 'demo-01', name: 'Presupuesto demostrativo A.pdf', type: 'Presupuesto de obra', date: '08 ago 2026', records: 48, status: 'Necesita revisión' },
  { id: 'demo-02', name: 'Presupuesto demostrativo B.pdf', type: 'Presupuesto de obra', date: '07 ago 2026', records: 32, status: 'Listo' },
  { id: 'demo-03', name: 'Presupuesto en proceso.pdf', type: 'Presupuesto de obra', date: '06 ago 2026', records: null, status: 'Procesando' },
  { id: 'demo-04', name: 'Presupuesto con error.pdf', type: 'Presupuesto de obra', date: '05 ago 2026', records: null, status: 'No se pudo procesar' },
  { id: 'demo-05', name: 'Presupuesto recibido.pdf', type: 'Presupuesto de obra', date: '04 ago 2026', records: null, status: 'Recibido' },
]

export const processingSteps = [
  'Preparando el documento',
  'Leyendo las páginas y aplicando OCR si es necesario',
  'Detectando tablas, campos y estructura',
  'Organizando y validando los datos extraídos',
]
