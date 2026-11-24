import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import css from '../src/styles/global.css?raw'
import { reachColumns, renderAt } from './testUtils'

describe('columnas, lenguaje y accesibilidad estructural', () => {
  it('renombra, reordena y restaura columnas', async () => {
    const { user } = await reachColumns()
    const labels = screen.getAllByLabelText('Título visible')
    await user.clear(labels[0])
    await user.type(labels[0], 'Código visible')
    expect(labels[0]).toHaveValue('Código visible')
    await user.click(screen.getByRole('button', { name: 'Mover Código visible abajo' }))
    expect(screen.getAllByLabelText('Título visible')[1]).toHaveValue('Código visible')
    await user.click(screen.getByRole('button', { name: 'Restaurar configuración' }))
    expect(screen.getAllByLabelText('Título visible')[0]).toHaveValue('Item')
  })

  it('guarda una plantilla sólo para la demostración', async () => {
    const { user } = await reachColumns()
    await user.click(screen.getByRole('button', { name: 'Guardar como plantilla' }))
    expect(screen.getByText('Plantilla guardada para esta demostración')).toHaveAttribute('role', 'status')
  })

  it('expone un asa accesible por columna y conserva botones alternativos', async () => {
    await reachColumns()
    const handles = screen.getAllByRole('button', { name: /Arrastrar columna/ })
    expect(handles).toHaveLength(7)
    handles[0].focus()
    expect(handles[0]).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Mover Item abajo' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Eliminar columna Item' })).not.toBeInTheDocument()
  })

  it('anuncia el cambio de posición al usar la alternativa accesible', async () => {
    const { user } = await reachColumns()
    await user.click(screen.getByRole('button', { name: 'Mover Item abajo' }))
    expect(screen.getByText('La columna Item se movió a la posición 2')).toHaveAttribute('role', 'status')
  })

  it('permite editar el nombre después de ordenar', async () => {
    const { user } = await reachColumns()
    await user.click(screen.getByRole('button', { name: 'Mover Item abajo' }))
    const movedName = screen.getAllByLabelText('Título visible')[1]
    await user.clear(movedName)
    await user.type(movedName, 'Código posterior')
    expect(screen.getByRole('button', { name: 'Arrastrar columna Código posterior' })).toBeVisible()
  })

  it('activa y cancela el sensor de teclado desde el asa', async () => {
    const { user } = await reachColumns()
    const handle = screen.getByRole('button', { name: 'Arrastrar columna Item' })
    handle.focus()
    await user.keyboard('{Enter}')
    await waitFor(() => expect(handle).toHaveAttribute('aria-pressed', 'true'))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(handle).toHaveAttribute('aria-pressed', 'false'))
  })

  it('añade una columna vinculada y permite eliminar sólo la creada', async () => {
    const { user } = await reachColumns()
    await user.click(screen.getByRole('button', { name: '+ Añadir columna' }))
    await user.type(screen.getByLabelText('Nombre de la columna'), 'Categoría personalizada')
    expect(screen.getByLabelText('Campo detectado')).toHaveValue('category')
    await user.click(screen.getByRole('button', { name: 'Añadir columna' }))
    expect(screen.getByLabelText('Título visible', { selector: '#label-user_categoria_personalizada' })).toHaveValue('Categoría personalizada')
    await user.click(screen.getByRole('button', { name: 'Eliminar columna Categoría personalizada' }))
    expect(screen.queryByDisplayValue('Categoría personalizada')).not.toBeInTheDocument()
  })

  it('valida nombre obligatorio y duplicado sin perder la configuración', async () => {
    const { user } = await reachColumns()
    await user.click(screen.getByRole('button', { name: '+ Añadir columna' }))
    await user.click(screen.getByRole('button', { name: 'Añadir columna' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Escribe un nombre')
    await user.type(screen.getByLabelText('Nombre de la columna'), 'Item')
    await user.click(screen.getByRole('button', { name: 'Añadir columna' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Ya existe una columna')
    expect(screen.getAllByLabelText('Título visible')).toHaveLength(7)
  })

  it('añade columnas de valor fijo y vacía completamente en memoria', async () => {
    const { user } = await reachColumns()
    await user.click(screen.getByRole('button', { name: '+ Añadir columna' }))
    await user.type(screen.getByLabelText('Nombre de la columna'), 'Sede')
    await user.click(screen.getByRole('radio', { name: /Usar el mismo valor/ }))
    await user.type(screen.getByLabelText('Valor fijo'), 'Lima')
    await user.click(screen.getByRole('button', { name: 'Añadir columna' }))
    const fixed = screen.getByRole('region', { name: 'Configurar columna Sede' })
    expect(within(fixed).getByText(/Origen: valor fijo/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '+ Añadir columna' }))
    await user.type(screen.getByLabelText('Nombre de la columna'), 'Notas')
    await user.click(screen.getByRole('radio', { name: /Dejarla vacía/ }))
    await user.click(screen.getByRole('button', { name: 'Añadir columna' }))
    expect(screen.getByRole('region', { name: 'Configurar columna Notas' })).toHaveTextContent('Origen: columna vacía')
  })

  it('mantiene la edición al volver a procesamiento y regresar', async () => {
    const { user } = await reachColumns()
    const first = screen.getAllByLabelText('Título visible')[0]
    await user.clear(first)
    await user.type(first, 'Código de fila')
    await user.click(screen.getByRole('button', { name: '← Volver' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a columnas' }))
    expect(screen.getAllByLabelText('Título visible')[0]).toHaveValue('Código de fila')
  })

  it('mueve el foco al título al cambiar de ruta', async () => {
    const { user } = renderAt('/')
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveFocus())
    await user.click(screen.getByRole('link', { name: 'Documentos' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Documentos' })).toHaveFocus())
  })

  it('muestra todos los estados con icono y texto', () => {
    renderAt('/documentos')
    for (const status of ['Recibido', 'Listo', 'Necesita revisión', 'Procesando', 'No se pudo procesar']) {
      expect(screen.getAllByText(status).length).toBeGreaterThan(0)
    }
  })

  it('ofrece labels visibles para búsqueda, filtro, archivo y tipo', () => {
    renderAt('/documentos/nuevo')
    expect(screen.getByLabelText('Seleccionar documento PDF')).toBeInTheDocument()
    expect(screen.getByLabelText('Tipo documental sugerido')).toBeVisible()
  })

  it('incluye soporte explícito para movimiento reducido, tamaños móviles y safe areas', () => {
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toContain('@media (max-width: 48rem)')
    expect(css).toContain('@media (max-width: 22.4375rem)')
    expect(css).toContain('min-width: 0')
    expect(css).toContain('min-height: 2.75rem')
    expect(css).toContain('env(safe-area-inset-bottom')
    expect(css).not.toMatch(/body\s*\{[^}]*overflow-x:\s*hidden/)
    expect(css).toContain('font-family: "IBM Plex Sans", Inter, system-ui')
    expect(css).toContain('--quipta-teal: #087f8c')
    expect(css).toContain('outline: 2px solid var(--focus)')
  })

  it.each([320, 360, 390, 768, 1024, 1440])('renderiza acciones esenciales a %i px', async (width) => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
    renderAt('/')
    expect(screen.getByRole('button', { name: 'Subir presupuesto en PDF' })).toBeVisible()
    expect(document.documentElement.lang).toBe('es')
  })
})
