import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { getLocalJobReview, saveLocalDecisions } from '../src/api/localJobs'
import { renderAt } from './testUtils'

describe('revisión editable local', () => {
  it('pagina la revisión y guarda decisiones sólo con el marcador local', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: '2', job_id: 'job-1', status: 'REVISAR', review_revision: 0, total_count: 101, requires_decision_count: 1, pending_decision_count: 1, offset: 25, limit: 25, result_expires_at: '2026-01-01T00:00:00Z', observations: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ review_revision: 1, pending_decision_count: 0 }), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    expect((await getLocalJobReview('job-1', 25)).total_count).toBe(101)
    await saveLocalDecisions('job-1', 0, [{ observation_id: 'obs-1', action: 'keep_original' }])
    expect(fetchSpy).toHaveBeenNthCalledWith(1, '/api/v1/local/jobs/job-1/review?offset=25&limit=25', { headers: { 'X-Local-Pilot': '1' } })
    expect(fetchSpy.mock.calls[1][1].headers).toMatchObject({ 'X-Local-Pilot': '1' })
  })

  it('muestra sólo edición manual, guarda y refleja la decisión en la tabla', async () => {
    const columns = [{ key: 'item', label: 'Ítem', data_type: 'text', included: true, position: 0, origin: 'standard' }, { key: 'description', label: 'Descripción', data_type: 'text', included: true, position: 1, origin: 'standard' }]
    const observation = { id: 'table-obs', state: 'PENDING', kind: 'code', page: 2, row: { order: 4, type: 'partida', label: 'Excavación' }, field: 'code', extracted_value: '', suggestion: null, reason: 'Código incompleto', evidence: [], allowed_actions: ['set_value'], requires_decision: true, target: { scope: 'cell', column_key: 'item' }, decision: null, resolved_value: null }
    const pending = { schema_version: '3', job_id: 'job-table', review_revision: 0, pending_decision_count: 1, filter: 'pending', offset: 0, limit: 25, total_count: 1, columns, rows: [{ row_key: '2:4', page: 2, order: 4, cells: { item: 'A.01', description: 'Excavación' }, observations: [observation] }] }
    const resolved = { ...pending, review_revision: 1, pending_decision_count: 0, rows: [{ ...pending.rows[0], observations: [{ ...observation, state: 'RESOLVED', decision: { action: 'set_value', value: 'A.01' }, resolved_value: 'A.01' }] }] }
    const fetchSpy = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(pending), { status: 200 })).mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify({ review_revision: 1, pending_decision_count: 0 }), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify(resolved), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    vi.spyOn(window, 'prompt').mockReturnValue('A.01')
    const { user } = renderAt('/documentos/local/job-table/revision')
    await user.click(await screen.findByText('A.01'))
    expect(await screen.findByText('Esta observación requiere que ingreses un valor manual.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Mantener original' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Editar valor' }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(4))
    expect(fetchSpy.mock.calls[2][0]).toBe('/api/v1/local/jobs/job-table/review/decisions')
    expect(await screen.findByRole('heading', { name: 'Decisión guardada' })).toBeVisible()
  })

  it('explica que una revisión de fila no modifica columnas', async () => {
    const columns = [{ key: 'item', label: 'Ítem', data_type: 'text', included: true, position: 0, origin: 'standard' }]
    const observation = { id: 'row-obs', state: 'PENDING', kind: 'row', page: 2, row: { order: 4, type: 'partida', label: 'Excavación' }, field: 'row', extracted_value: 'Texto combinado', suggestion: null, reason: 'No se separó la fila', evidence: [], allowed_actions: ['keep_original', 'set_value'], requires_decision: true, target: { scope: 'row' }, decision: null, resolved_value: null }
    const table = { schema_version: '3', job_id: 'job-row', review_revision: 0, pending_decision_count: 1, filter: 'pending', offset: 0, limit: 25, total_count: 1, columns, rows: [{ row_key: '2:4', page: 2, order: 4, cells: { item: 'A.01' }, observations: [observation] }] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(table), { status: 200 })))
    const { user } = renderAt('/documentos/local/job-row/revision')
    await user.click(await screen.findByRole('button', { name: 'Revisar fila' }))
    expect(await screen.findByText('La confirmación se registra para la revisión y no modifica columnas de esta fila.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Registrar valor de revisión' })).toBeVisible()
  })

  it('aplica un lote compatible en un solo PUT y conserva la decisión al refrescar', async () => {
    const columns = [{ key: 'item', label: 'Ítem', data_type: 'text', included: true, position: 0, origin: 'standard' }]
    const first = { id: 'first', state: 'PENDING', kind: 'code', page: 2, row: { order: 1, type: 'partida', label: 'Primera' }, field: 'code', extracted_value: 'A.01', suggestion: { value: 'A.O1', confidence: 'MEDIA' }, reason: 'Ambiguo', evidence: [], allowed_actions: ['keep_original', 'accept_suggestion'], requires_decision: true, target: { scope: 'cell', column_key: 'item' }, decision: null, resolved_value: null }
    const second = { ...first, id: 'second', row: { order: 2, type: 'partida', label: 'Segunda' }, extracted_value: 'B.01', suggestion: { value: 'B.O1', confidence: 'MEDIA' } }
    const pending = { schema_version: '3', job_id: 'job-batch', review_revision: 0, pending_decision_count: 2, filter: 'pending', offset: 0, limit: 25, total_count: 2, columns, rows: [{ row_key: '2:1', page: 2, order: 1, cells: { item: 'A.01' }, observations: [first] }, { row_key: '2:2', page: 2, order: 2, cells: { item: 'B.01' }, observations: [second] }] }
    const refreshed = { ...pending, review_revision: 1, pending_decision_count: 0, total_count: 0, rows: [] }
    const persisted = { ...pending, review_revision: 1, pending_decision_count: 0, rows: pending.rows.map(item => ({ ...item, observations: item.observations.map(observation => ({ ...observation, state: 'RESOLVED', decision: { action: 'keep_original', value: observation.extracted_value }, resolved_value: observation.extracted_value })) })) }
    const fetchSpy = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(pending), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify({ review_revision: 1, pending_decision_count: 0 }), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify(refreshed), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify(persisted), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const view = renderAt('/documentos/local/job-batch/revision')
    const { user } = view

    await user.click((await screen.findAllByRole('checkbox', { name: /Seleccionar Ítem/ }))[0])
    await user.click(screen.getAllByRole('checkbox', { name: /Seleccionar Ítem/ })[1])
    await user.click(screen.getByRole('button', { name: 'Aplicar por lote: mantener detectados' }))
    expect(screen.getByText(/Se aplicarán 2 decisiones para mantener los valores detectados/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Confirmar lote' }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(3))
    const putCalls = fetchSpy.mock.calls.filter(([, request]) => request?.method === 'PUT')
    expect(putCalls).toHaveLength(1)
    expect(putCalls[0][1]?.body).toContain('"observation_id":"first"')
    expect(putCalls[0][1]?.body).toContain('"observation_id":"second"')
    expect(await screen.findByText('Se aplicaron 2 decisiones')).toBeVisible()
    view.unmount()
    renderAt('/documentos/local/job-batch/revision')
    await waitFor(() => expect(screen.getAllByRole('cell', { name: 'Resuelta' })).toHaveLength(2))
  })

  it('no habilita lote para alcances incompatibles y muestra ambos valores con el PDF en su página', async () => {
    const columns = [{ key: 'item', label: 'Ítem', data_type: 'text', included: true, position: 0, origin: 'standard' }]
    const cell = { id: 'cell', state: 'PENDING', kind: 'code', page: 4, row: { order: 1, type: 'partida', label: 'Primera' }, field: 'code', extracted_value: 'A.01', suggestion: { value: 'A.O1', confidence: 'MEDIA' }, reason: 'Ambiguo', evidence: [], allowed_actions: ['keep_original'], requires_decision: true, target: { scope: 'cell', column_key: 'item' }, decision: null, resolved_value: null }
    const row = { ...cell, id: 'row', field: 'row', target: { scope: 'row' }, extracted_value: 'Fila combinada', suggestion: null }
    const table = { schema_version: '3', job_id: 'job-viewer', review_revision: 0, pending_decision_count: 2, filter: 'pending', offset: 0, limit: 25, total_count: 2, columns, rows: [{ row_key: '4:1', page: 4, order: 1, cells: { item: 'A.01' }, observations: [cell] }, { row_key: '4:2', page: 4, order: 2, cells: { item: 'A.02' }, observations: [row] }] }
    const fetchSpy = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(table), { status: 200 })).mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const OriginalURL = URL
    class TestURL extends OriginalURL {
      static createObjectURL = vi.fn(() => 'blob:review-source')
      static revokeObjectURL = vi.fn()
    }
    vi.stubGlobal('URL', TestURL)
    const { user } = renderAt('/documentos/local/job-viewer/revision')

    const checkboxes = await screen.findAllByRole('checkbox', { name: /Seleccionar/ })
    await user.click(checkboxes[0])
    await user.click(checkboxes[1])
    expect(screen.queryByRole('button', { name: /Aplicar por lote/ })).not.toBeInTheDocument()
    await user.click(screen.getByText('A.01'))
    expect(await screen.findByText('Valor detectado')).toBeVisible()
    expect(screen.getByText('A.O1')).toBeVisible()
    await waitFor(() => expect(screen.getByTitle('PDF fuente local')).toHaveAttribute('src', 'blob:review-source#page=4'))
  })
})
