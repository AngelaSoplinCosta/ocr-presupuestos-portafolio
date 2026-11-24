import { expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderAt } from './testUtils'

it('ordena los descriptores serializables antes de guardarlos', async () => {
  const initial = { export_revision: 0, source_review_revision: 0, pending_decision_count: 0, simple_result_available: false, columns: [{ key: 'item', label: 'Ítem', data_type: 'text', included: true, position: 0, origin: 'standard' }, { key: 'supplier', label: 'Proveedor', data_type: 'text', included: true, position: 1, origin: 'candidate' }] }
  const fetchSpy = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(initial), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify({ ...initial, export_revision: 1 }), { status: 200 }))
  vi.stubGlobal('fetch', fetchSpy)
  const { user } = renderAt('/documentos/local/job-1/columnas')
  await screen.findByDisplayValue('Proveedor')
  await user.click(screen.getByRole('button', { name: 'Subir Proveedor' }))
  await user.click(screen.getByRole('button', { name: 'Continuar al Excel' }))
  expect(fetchSpy.mock.calls[1][1].body).toContain('"key":"supplier"')
})
