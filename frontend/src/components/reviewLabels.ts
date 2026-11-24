import type { ExportColumn } from '../types'

const fieldLabels: Record<string, string> = {
  item: 'Ítem',
  code: 'Ítem',
  description: 'Descripción',
  unit: 'Unidad',
  quantity: 'Metrado',
  unit_price: 'Precio unitario',
  amount: 'Parcial',
  row: 'Revisión de fila no separada',
}

export function humanFieldLabel(field: string) {
  return fieldLabels[field] ?? 'Dato detectado'
}

export function humanColumnLabel(column: ExportColumn) {
  return fieldLabels[column.key] ?? column.label
}
