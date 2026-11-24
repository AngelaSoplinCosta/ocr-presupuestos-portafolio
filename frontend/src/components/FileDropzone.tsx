import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { Button } from './Button'

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024

function validateFile(file: File): string {
  if (!file.name.toLowerCase().endsWith('.pdf') || file.type !== 'application/pdf') return 'Este archivo no tiene un formato admitido. Selecciona un PDF para continuar.'
  if (file.size === 0) return 'Este PDF no contiene datos. Puedes seleccionar otro archivo.'
  if (file.size > MAX_UPLOAD_BYTES) return 'Este PDF supera el máximo de 50 MB. Puedes seleccionar una versión de menor tamaño.'
  return ''
}

export function FileDropzone({ file, onFile }: { file: File | null; onFile: (file: File | null) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)

  const accept = (candidate?: File) => {
    if (!candidate) return
    const message = validateFile(candidate)
    setError(message)
    if (!message) onFile(candidate)
  }

  const onChange = (event: ChangeEvent<HTMLInputElement>) => accept(event.target.files?.[0])
  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    accept(event.dataTransfer.files[0])
  }

  return (
    <div>
      <div
        className={`dropzone ${dragging ? 'dropzone--dragging' : ''}`}
        aria-label="Zona para cargar un PDF"
        onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input ref={inputRef} id="document-file" className="visually-hidden-input" type="file" accept="application/pdf,.pdf" onChange={onChange} aria-label="Seleccionar documento PDF" aria-describedby="file-help file-error" tabIndex={-1} />
        {!file ? (
          <>
            <span className="dropzone__icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 2.75h7l5 5v13.5H6z" /><path d="M13 2.75v5h5M12 17v-6m-3 3 3-3 3 3" /></svg></span>
            <h2>Arrastra tu PDF aquí</h2>
            <p id="file-help">o selecciónalo desde tu equipo</p>
            <Button type="button" onClick={() => inputRef.current?.click()}>Seleccionar PDF</Button>
            <ul className="dropzone__limits" aria-label="Requisitos del archivo">
              <li>Formato: PDF</li>
              <li>Máximo: 50 MB</li>
              <li>Presupuesto de obra</li>
            </ul>
          </>
        ) : (
          <div className="file-summary">
            <span className="file-summary__icon" aria-hidden="true">PDF</span>
            <div><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></div>
            <Button type="button" variant="quiet" onClick={() => { onFile(null); setError(''); if (inputRef.current) inputRef.current.value = '' }}>Retirar archivo</Button>
          </div>
        )}
      </div>
      <p id="file-error" className="field-error" role={error ? 'alert' : undefined} aria-live={error ? 'assertive' : undefined}>{error}</p>
    </div>
  )
}
