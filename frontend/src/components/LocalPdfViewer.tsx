import { useCallback, useEffect, useRef, useState } from 'react'

const LOCAL_PILOT_HEADER = 'X-Local-Pilot'

export function LocalPdfViewer({ jobId, page }: { jobId: string; page: number | null }) {
  const objectUrl = useRef<string | null>(null)
  const [pdf, setPdf] = useState<{ jobId: string; url: string } | null>(null)
  const [failedJobId, setFailedJobId] = useState<string | null>(null)
  const [closedJobId, setClosedJobId] = useState<string | null>(null)
  const isOpen = closedJobId !== jobId
  const targetPage = Number.isInteger(page) && page !== null && page > 0 ? page : null

  const revokePdfUrl = useCallback(() => {
    if (objectUrl.current) {
      URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = null
    }
  }, [])

  useEffect(() => {
    if (!isOpen) return

    const controller = new AbortController()
    let cancelled = false
    void fetch(`/api/v1/local/jobs/${encodeURIComponent(jobId)}/source`, {
      headers: { [LOCAL_PILOT_HEADER]: '1' },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('SOURCE_UNAVAILABLE')
        return response.blob()
      })
      .then((blob) => {
        const nextUrl = URL.createObjectURL(blob)
        if (cancelled) {
          URL.revokeObjectURL(nextUrl)
          return
        }
        revokePdfUrl()
        objectUrl.current = nextUrl
        setPdf({ jobId, url: nextUrl })
      })
      .catch(() => {
        if (!cancelled) setFailedJobId(jobId)
      })

    return () => {
      cancelled = true
      controller.abort()
      revokePdfUrl()
    }
  }, [isOpen, jobId, revokePdfUrl])

  if (!isOpen) return null
  if (failedJobId === jobId) return <p role="alert">No se pudo cargar el PDF local.</p>
  const pdfUrl = pdf?.jobId === jobId ? pdf.url : null

  return (
    <section aria-label="PDF fuente local">
      <button type="button" onClick={() => { revokePdfUrl(); setPdf(null); setFailedJobId(null); setClosedJobId(jobId) }}>Cerrar visor</button>
      {pdfUrl ? <iframe title="PDF fuente local" src={targetPage ? `${pdfUrl}#page=${targetPage}` : pdfUrl} /> : <p>Cargando PDF local…</p>}
    </section>
  )
}
