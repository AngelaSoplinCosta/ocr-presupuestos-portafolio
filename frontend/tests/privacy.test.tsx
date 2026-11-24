import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { reachColumns, renderAt } from './testUtils'
import { networkSpies } from './setup'

const sourceFiles = import.meta.glob('../src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('privacidad y ausencia de red', () => {
  it('no invoca APIs de red al recorrer pantallas', async () => {
    const { user } = renderAt('/')
    await user.click(screen.getAllByRole('button', { name: 'Probar con un documento de ejemplo' })[0])
    await user.click(screen.getByRole('button', { name: 'Mostrar información detectada' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a columnas' }))
    await user.click(screen.getByRole('button', { name: 'Continuar a revisión' }))
    expect(networkSpies.fetch).not.toHaveBeenCalled()
    expect(networkSpies.xhrOpen).not.toHaveBeenCalled()
    expect(networkSpies.sendBeacon).not.toHaveBeenCalled()
    expect(networkSpies.webSocket).not.toHaveBeenCalled()
  })

  it('no usa persistencia, lectura de archivos ni consola y limita las URL temporales a descargas y al visor local', () => {
    const source = Object.values(sourceFiles).join('\n')
    const resultSource = Object.entries(sourceFiles).find(([path]) => path.endsWith('/pages/ResultPage.tsx'))?.[1] ?? ''
    const viewerSource = Object.entries(sourceFiles).find(([path]) => path.endsWith('/components/LocalPdfViewer.tsx'))?.[1] ?? ''
    const sourceWithoutTemporaryUrlOwners = Object.entries(sourceFiles)
      .filter(([path]) => !path.endsWith('/pages/ResultPage.tsx') && !path.endsWith('/components/LocalPdfViewer.tsx'))
      .map(([, contents]) => contents)
      .join('\n')
    expect(source).not.toMatch(/localStorage|sessionStorage/)
    expect(source).not.toMatch(/FileReader/)
    expect(sourceWithoutTemporaryUrlOwners).not.toMatch(/createObjectURL|revokeObjectURL/)
    expect(resultSource).toMatch(/URL\.createObjectURL/)
    expect(resultSource).toMatch(/URL\.revokeObjectURL/)
    expect(viewerSource).toMatch(/URL\.createObjectURL/)
    expect(viewerSource).toMatch(/URL\.revokeObjectURL/)
    expect(source).not.toMatch(/console\.(log|info|debug|warn|error)/)
    expect(source).not.toMatch(/X-API-Key|api[_-]?key|client[_-]?secret|HMAC|bearer\s+/i)
  })

  it('no persiste decisiones durante el recorrido', async () => {
    const localSpy = vi.spyOn(Storage.prototype, 'setItem')
    const { user } = await reachColumns()
    await user.click(screen.getByRole('button', { name: 'Guardar como plantilla' }))
    expect(localSpy).not.toHaveBeenCalled()
  })

  it('mantiene visible el aviso de privacidad en la carga', () => {
    renderAt('/documentos/nuevo')
    expect(screen.getByText(/el PDF se envía a la API local/i)).toBeVisible()
    expect(screen.getByText(/recargar la página no elimina esa copia/i)).toBeVisible()
  })
})
