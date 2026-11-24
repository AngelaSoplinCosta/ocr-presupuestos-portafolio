import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { renderAt } from './testUtils'

const columns = [
  { key: 'item', label: 'Ítem', data_type: 'text', included: true, position: 0, origin: 'standard' },
  { key: 'description', label: 'Descripción', data_type: 'text', included: true, position: 1, origin: 'standard' },
  { key: 'unit', label: 'Unidad', data_type: 'text', included: true, position: 2, origin: 'standard' },
  { key: 'quantity', label: 'Metrado', data_type: 'decimal', included: true, position: 3, origin: 'standard' },
  { key: 'unit_price', label: 'Precio unitario', data_type: 'currency', included: true, position: 4, origin: 'standard' },
  { key: 'amount', label: 'Parcial', data_type: 'currency', included: true, position: 5, origin: 'standard' },
]

function structuredField(key: string, label: string, overrides = {}) {
  return { key, label, ocr_value: key === 'item' ? '701.4' : key === 'description' ? 'MATERIAL SINTETICO DE PRUEBA' : key === 'unit' ? 'kg' : key === 'quantity' ? '24,680.25' : key === 'unit_price' ? '12.40' : '306,035.10', provisional_value: key === 'item' ? '701.A' : key === 'description' ? 'MATERIAL SINTETICO DE PRUEBA' : key === 'unit' ? 'kg' : key === 'quantity' ? '24680.25' : key === 'unit_price' ? '12.40' : '306035.10', suggestion: key === 'item' ? { value: '701.A', confidence: 'LEGACY' } : null, differs_from_ocr: key === 'item', state: 'PENDING', decision: null, can_confirm_provisional: key !== 'item', manual_only: false, ...overrides }
}

function tableWithStructured(fields = [structuredField('item', 'Ítem'), structuredField('description', 'Descripción'), structuredField('unit', 'Unidad'), structuredField('quantity', 'Metrado'), structuredField('unit_price', 'Precio unitario'), structuredField('amount', 'Parcial')]) {
  const observation = { id: 'row-ocr', state: 'PENDING', kind: 'row', page: 4, row: { order: 2, type: 'partida', label: 'Insumo ficticio' }, field: 'row', extracted_value: '701.4 MATERIAL SINTETICO DE PRUEBA kg 24,680.25 12.40 306,035.10', suggestion: null, reason: 'candidato: 701.A', evidence: [], allowed_actions: ['keep_original', 'set_value'], requires_decision: true, target: { scope: 'row' }, decision: null, resolved_value: null }
  return { schema_version: '4', job_id: 'structured-job', review_revision: 0, pending_decision_count: 6, filter: 'pending', offset: 0, limit: 25, total_count: 1, columns, rows: [{ row_key: '4:2', page: 4, order: 2, cells: { item: '701.A', description: 'MATERIAL SINTETICO DE PRUEBA', unit: 'kg', quantity: '24680.25', unit_price: '12.40', amount: '306035.10' }, observations: [observation], structured_review: { observation_id: 'row-ocr', raw_ocr_line: observation.extracted_value, fields, confirmed_field_count: fields.filter(field => field.state === 'RESOLVED').length, pending_field_count: fields.filter(field => field.state === 'PENDING').length, legacy_row_decision: null } }] }
}

describe('revisión estructurada de fila OCR', () => {
  it('muestra evidencia, progreso y confirma en un único PUT sólo los campos seguros', async () => {
    const table = tableWithStructured()
    const fetchSpy = vi.fn((path: string, request?: RequestInit) => {
      if (path.endsWith('/source')) return Promise.resolve(new Response(new Uint8Array([1, 2, 3]), { status: 200 }))
      if (request?.method === 'PUT') return Promise.resolve(new Response(JSON.stringify({ review_revision: 1, pending_decision_count: 1 }), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify(table), { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchSpy)
    const OriginalURL = URL
    class TestURL extends OriginalURL { static createObjectURL = vi.fn(() => 'blob:structured'); static revokeObjectURL = vi.fn() }
    vi.stubGlobal('URL', TestURL)
    const { user } = renderAt('/documentos/local/structured-job/revision')

    await user.click(await screen.findByRole('button', { name: 'Revisar fila estructurada' }))
    expect(await screen.findByText('Evidencia OCR original')).toBeVisible()
    expect(screen.getByText('701.4 MATERIAL SINTETICO DE PRUEBA kg 24,680.25 12.40 306,035.10')).toBeVisible()
    expect(within(screen.getByRole('complementary')).getByText('0 de 6 campos confirmados')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Aceptar “701.A”' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Conservar “701.A”' })).toBeVisible()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    const descriptionCard = screen.getByLabelText('Revisión de Descripción')
    const descriptionValue = within(descriptionCard).getByText('Valor provisional').parentElement?.querySelector('dd')
    const quantityCard = screen.getByLabelText('Revisión de Metrado')
    const quantityValue = within(quantityCard).getByText('Valor provisional').parentElement?.querySelector('dd')
    expect(descriptionValue).not.toHaveClass('numeric-value')
    expect(quantityValue).toHaveClass('numeric-value')

    await user.click(screen.getByRole('button', { name: 'Confirmar 5 campos provisionales' }))
    expect(screen.getByText('Se confirmarán 5 campos provisionales. 1 requieren revisión individual.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Confirmar campos provisionales' }))
    await waitFor(() => expect(fetchSpy.mock.calls.some(([path, request]) => path.endsWith('/review/decisions') && request?.method === 'PUT')).toBe(true))
    const put = fetchSpy.mock.calls.find(([path, request]) => path.endsWith('/review/decisions') && request?.method === 'PUT')
    expect(put?.[1]?.body).toContain('"action":"confirm_provisional_row"')
    expect(put?.[1]?.body).not.toContain('"field":"item"')
  })

  it('deja un campo no separable sólo con edición manual y conserva las tarjetas verticales', async () => {
    const fields = [structuredField('item', 'Ítem', { ocr_value: null, suggestion: null, differs_from_ocr: null, can_confirm_provisional: false, manual_only: true }), ...['description', 'unit', 'quantity', 'unit_price', 'amount'].map((key, index) => structuredField(key, columns[index + 1].label, { state: 'RESOLVED', decision: { action: 'confirm_provisional', value: 'confirmado' }, can_confirm_provisional: false }))]
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(path.endsWith('/source') ? new Response(new Uint8Array([1]), { status: 200 }) : new Response(JSON.stringify(tableWithStructured(fields)), { status: 200 }))))
    const OriginalURL = URL
    class TestURL extends OriginalURL { static createObjectURL = vi.fn(() => 'blob:structured'); static revokeObjectURL = vi.fn() }
    vi.stubGlobal('URL', TestURL)
    const { user } = renderAt('/documentos/local/structured-job/revision')

    await user.click(await screen.findByRole('button', { name: 'Revisar fila estructurada' }))
    expect(await screen.findByText('OCR no separable: ingresa un valor manual válido para confirmar este campo.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Editar Ítem' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Conservar “701.A”' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Revisión de Ítem')).toHaveClass('structured-review-field')
  })

  it('cierra el drawer cuando la fila resuelta desaparece de pendientes', async () => {
    const fields = [structuredField('item', 'Ítem'), ...['description', 'unit', 'quantity', 'unit_price', 'amount'].map((key, index) => structuredField(key, columns[index + 1].label, { state: 'RESOLVED', decision: { action: 'confirm_provisional', value: 'confirmado' }, can_confirm_provisional: false }))]
    const pending = tableWithStructured(fields)
    pending.pending_decision_count = 1
    pending.rows[0].structured_review.pending_field_count = 1
    pending.rows[0].structured_review.confirmed_field_count = 5
    const resolved = { ...pending, review_revision: 1, pending_decision_count: 0, total_count: 0, rows: [] }
    let tableRequests = 0
    vi.stubGlobal('fetch', vi.fn((path: string, request?: RequestInit) => {
      if (path.endsWith('/source')) return Promise.resolve(new Response(new Uint8Array([1]), { status: 200 }))
      if (request?.method === 'PUT') return Promise.resolve(new Response(JSON.stringify({ review_revision: 1, pending_decision_count: 0 }), { status: 200 }))
      if (path.includes('/review/table')) return Promise.resolve(new Response(JSON.stringify(tableRequests++ === 0 ? pending : resolved), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify(resolved), { status: 200 }))
    }))
    const OriginalURL = URL
    class TestURL extends OriginalURL { static createObjectURL = vi.fn(() => 'blob:structured'); static revokeObjectURL = vi.fn() }
    vi.stubGlobal('URL', TestURL)
    const { user } = renderAt('/documentos/local/structured-job/revision')

    await user.click(await screen.findByRole('button', { name: 'Revisar fila estructurada' }))
    await user.click(screen.getByRole('button', { name: 'Conservar “701.A”' }))
    expect(await screen.findByText('Selecciona una celda o fila resaltada para revisar la decisión.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Conservar “701.A”' })).not.toBeInTheDocument()
  })
})
