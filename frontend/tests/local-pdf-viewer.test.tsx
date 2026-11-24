import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LocalPdfViewer } from '../src/components/LocalPdfViewer'

describe('LocalPdfViewer', () => {
  it('solicita el PDF local, abre la página observada y revoca URLs temporales', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200 }))
      .mockResolvedValueOnce(new Response(new Uint8Array([4, 5, 6]), { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    const createObjectURL = vi.fn()
      .mockReturnValueOnce('blob:quipta-source-1')
      .mockReturnValueOnce('blob:quipta-source-2')
    const revokeObjectURL = vi.fn()
    const OriginalURL = URL
    class TestURL extends OriginalURL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    }
    vi.stubGlobal('URL', TestURL)

    const view = render(<LocalPdfViewer jobId="job-1" page={3} />)

    await waitFor(() => expect(screen.getByTitle('PDF fuente local')).toHaveAttribute('src', 'blob:quipta-source-1#page=3'))
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/local/jobs/job-1/source', {
      headers: { 'X-Local-Pilot': '1' },
      signal: expect.any(AbortSignal),
    })

    view.rerender(<LocalPdfViewer jobId="job-2" page={5} />)
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:quipta-source-1'))
    await waitFor(() => expect(screen.getByTitle('PDF fuente local')).toHaveAttribute('src', 'blob:quipta-source-2#page=5'))

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar visor' }))
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:quipta-source-2')
    expect(screen.queryByTitle('PDF fuente local')).not.toBeInTheDocument()
  })
})
