import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { reachColumns, renderAt, reachReview } from './testUtils'

describe('recorrido documental', () => {
  it('muestra el inicio Quipta con sus acciones principales', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: 'De presupuesto en PDF a Excel confiable' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Subir presupuesto en PDF' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Ver cómo funciona' })).toBeEnabled()
    expect(screen.getAllByRole('button', { name: 'Probar con un documento de ejemplo' }).length).toBeGreaterThan(0)
  })

  it('permite completar el recorrido de ejemplo sin avance automático', async () => {
    const { user } = renderAt('/')
    await user.click(screen.getAllByRole('button', { name: 'Probar con un documento de ejemplo' })[0])
    expect(screen.getByRole('heading', { name: 'Procesamiento simulado' })).toBeInTheDocument()
    expect(screen.getByText('Demostración: esta pantalla todavía no está conectada al motor de procesamiento.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continuar a columnas' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mostrar información detectada' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a columnas' }))
    expect(screen.getByRole('heading', { name: 'Elige y organiza las columnas' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continuar a revisión' }))
    const finish = screen.getByRole('button', { name: 'Finalizar revisión' })
    expect(finish).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Cargar decisiones de ejemplo' }))
    expect(finish).toBeEnabled()
    await user.click(finish)
    expect(screen.getByRole('heading', { name: 'Documento preparado' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Descargar CSV' })).toBeDisabled()
  })

  it('presenta las cuatro etapas explícitas y no avanza por tiempo', async () => {
    const { user } = renderAt('/')
    await user.click(screen.getAllByRole('button', { name: 'Probar con un documento de ejemplo' })[0])
    for (const stage of ['Preparando el documento', 'Leyendo las páginas y aplicando OCR si es necesario', 'Detectando tablas, campos y estructura', 'Organizando y validando los datos extraídos']) {
      expect(screen.getByText(stage)).toBeVisible()
    }
    await new Promise((resolve) => window.setTimeout(resolve, 20))
    expect(screen.getByRole('button', { name: 'Mostrar información detectada' })).toBeEnabled()
  })

  it('bloquea revisión hasta confirmar columnas', async () => {
    const { user } = renderAt('/')
    await user.click(screen.getAllByRole('button', { name: 'Probar con un documento de ejemplo' })[0])
    await user.click(screen.getByRole('button', { name: 'Mostrar información detectada' }))
    window.history.pushState({}, '', '/documentos/demo/revision')
    fireEvent.popState(window)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Elige y organiza las columnas' })).toBeInTheDocument())
  })

  it('filtra observaciones de columnas excluidas y conserva la crítica general', async () => {
    const { user } = await reachColumns()
    for (const label of ['Parcial', 'Metrado', 'Unidad']) {
      const row = screen.getByRole('region', { name: `Configurar columna ${label}` })
      await user.click(within(row).getByRole('checkbox', { name: 'Incluir' }))
    }
    await user.click(screen.getByRole('button', { name: 'Continuar a revisión' }))
    expect(screen.getByText('0 de 1 revisadas')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Conciliación general' })).toBeInTheDocument()
    expect(screen.getByText(/Incidencia general crítica/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Parcial' })).not.toBeInTheDocument()
  })

  it('refleja orden, nombres, valores fijos y vacíos en la vista previa final', async () => {
    const { user } = await reachColumns()
    const itemName = screen.getAllByLabelText('Título visible')[0]
    await user.clear(itemName)
    await user.type(itemName, 'Código')
    await user.click(screen.getByRole('button', { name: 'Mover Código abajo' }))

    await user.click(screen.getByRole('button', { name: '+ Añadir columna' }))
    await user.type(screen.getByLabelText('Nombre de la columna'), 'Sede')
    await user.click(screen.getByRole('radio', { name: /Usar el mismo valor/ }))
    await user.type(screen.getByLabelText('Valor fijo'), 'Lima')
    await user.click(screen.getByRole('button', { name: 'Añadir columna' }))
    await user.click(screen.getByRole('button', { name: '+ Añadir columna' }))
    await user.type(screen.getByLabelText('Nombre de la columna'), 'Notas')
    await user.click(screen.getByRole('radio', { name: /Dejarla vacía/ }))
    await user.click(screen.getByRole('button', { name: 'Añadir columna' }))

    await user.click(screen.getByRole('button', { name: 'Continuar a revisión' }))
    await user.click(screen.getByRole('button', { name: 'Cargar decisiones de ejemplo' }))
    await user.click(screen.getByRole('button', { name: 'Finalizar revisión' }))
    const table = screen.getByRole('table')
    const headers = within(table).getAllByRole('columnheader').map((header) => header.textContent)
    expect(headers.slice(0, 2)).toEqual(['Descripción', 'Código'])
    expect(headers.slice(-2)).toEqual(['Sede', 'Notas'])
    expect(within(table).getAllByText('Lima')).toHaveLength(2)
    expect(within(table).getAllByText('Vacío')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeDisabled()
  })

  it('selecciona y retira un PDF sin leerlo', async () => {
    const { user } = renderAt('/documentos/nuevo')
    const file = new File(['contenido no leído por la aplicación'], 'ejemplo.pdf', { type: 'application/pdf' })
    const input = screen.getByLabelText('Seleccionar documento PDF')
    await user.upload(input, file)
    expect(screen.getByText('ejemplo.pdf')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retirar archivo' }))
    expect(screen.queryByText('ejemplo.pdf')).not.toBeInTheDocument()
  })

  it('rechaza formatos distintos de PDF con orientación útil', async () => {
    renderAt('/documentos/nuevo')
    const input = screen.getByLabelText('Seleccionar documento PDF')
    fireEvent.change(input, { target: { files: [new File(['texto'], 'notas.txt', { type: 'text/plain' })] } })
    expect(screen.getByRole('alert')).toHaveTextContent('Este archivo no tiene un formato admitido')
  })

  it('rechaza un archivo vacío y uno que supera el límite', async () => {
    const { user } = renderAt('/documentos/nuevo')
    const input = screen.getByLabelText('Seleccionar documento PDF')
    await user.upload(input, new File([], 'vacio.pdf', { type: 'application/pdf' }))
    expect(screen.getByRole('alert')).toHaveTextContent('no contiene datos')
    const large = new File(['x'], 'grande.pdf', { type: 'application/pdf' })
    Object.defineProperty(large, 'size', { value: 50 * 1024 * 1024 + 1 })
    await user.upload(input, large)
    expect(screen.getByRole('alert')).toHaveTextContent('supera el máximo de 50 MB')
  })

  it('anuncia la ausencia de archivo y conserva la pantalla', async () => {
    const { user } = renderAt('/documentos/nuevo')
    await user.click(screen.getByRole('button', { name: 'Continuar a procesamiento' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Selecciona un PDF para continuar')
    expect(screen.getByRole('heading', { name: 'Sube tu presupuesto en PDF' })).toBeInTheDocument()
  })

  it('protege columnas y resultado cuando falta estado previo', async () => {
    renderAt('/documentos/nuevo/columnas')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sube tu presupuesto en PDF' })).toBeInTheDocument())
  })

  it('protege revisión y resultado cuando falta el estado previo', async () => {
    renderAt('/documentos/demo/revision')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sube tu presupuesto en PDF' })).toBeInTheDocument())
  })

  it('edita, cancela y conserva visible el valor original', async () => {
    const { user } = await reachReview()
    await user.click(screen.getByRole('button', { name: 'Editar manualmente' }))
    expect(screen.getByText(/Original:/)).toHaveTextContent('S/ 1,177.59')
    await user.clear(screen.getByLabelText('Nuevo valor'))
    await user.type(screen.getByLabelText('Nuevo valor'), 'valor inválido')
    await user.click(screen.getByRole('button', { name: 'Aplicar valor' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Revisa el formato')
    await user.click(screen.getByRole('button', { name: 'Cancelar edición' }))
    expect(screen.getByText('S/ 1,177.59')).toBeInTheDocument()
  })

  it('conserva el detectado y permite deshacer la decisión', async () => {
    const { user } = await reachReview()
    await user.click(screen.getByRole('button', { name: 'Conservar valor detectado' }))
    const summary = screen.getByRole('status', { name: 'Decisión aplicada' })
    expect(within(summary).getByText('S/ 1,177.59')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Deshacer decisión' }))
    expect(screen.getByRole('button', { name: 'Conservar valor detectado' })).toBeEnabled()
  })

  it('limpia el proceso al comenzar otro documento', async () => {
    const { user } = await reachReview()
    await user.click(screen.getByRole('button', { name: 'Cargar decisiones de ejemplo' }))
    await user.click(screen.getByRole('button', { name: 'Finalizar revisión' }))
    await user.click(screen.getByRole('button', { name: 'Procesar otro documento' }))
    expect(screen.getByRole('heading', { name: 'Sube tu presupuesto en PDF' })).toBeInTheDocument()
    expect(screen.queryByText('Datos de ejemplo')).not.toBeInTheDocument()
  })

  it('pide confirmación antes de salir con trabajo', async () => {
    const { user } = renderAt('/')
    await user.click(screen.getAllByRole('button', { name: 'Probar con un documento de ejemplo' })[0])
    vi.mocked(window.confirm).mockReturnValue(false)
    await user.click(screen.getByRole('button', { name: 'Salir del proceso' }))
    expect(window.confirm).toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: 'Procesamiento simulado' })).toBeInTheDocument()
  })

  it('acepta selección por evento de teclado del control nativo', async () => {
    renderAt('/documentos/nuevo')
    const input = screen.getByLabelText('Seleccionar documento PDF')
    input.focus()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(input).toHaveFocus()
  })
})
