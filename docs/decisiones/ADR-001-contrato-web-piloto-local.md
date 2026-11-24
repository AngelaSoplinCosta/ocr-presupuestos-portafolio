# ADR-001: contrato web del piloto local

- Estado: aceptado para la primera fase del MVP.
- Fecha: 2026-08-20.
- Alcance: contrato de datos entre el navegador y la API local del piloto.

## Decisión

El trabajo se representa con estos campos:

| Campo | Tipo | Regla |
| --- | --- | --- |
| `job_id` | UUID/string | Identidad interna del trabajo. |
| `document_type` | `budget` | Único tipo aceptado; se muestra como `Presupuesto de obra`. |
| `original_filename` | string | Nombre visible validado; nunca se usa como ruta física. |
| `status` | enum | `RECIBIDO`, `PROCESANDO`, `COMPLETADO`, `REVISAR`, `ERROR`. |
| `error_code` | enum/string nullable | Código sanitizado cuando corresponda. |
| `requires_review` | boolean | `true` únicamente para `REVISAR`. |
| `result_available` | boolean | Indica si el resultado puede descargarse. |
| `result_expires_at` | datetime nullable | Expiración del resultado, en UTC. |
| `created_at` | datetime | Fecha de creación, en UTC. |
| `updated_at` | datetime | Última actualización, en UTC. |

Los textos visibles son, respectivamente: `Recibido`, `Procesando`, `Listo`, `Necesita revisión` y `No se pudo procesar`.

Los códigos de error compartidos son:

`INVALID_PDF`, `FILE_TOO_LARGE`, `UNSUPPORTED_DOCUMENT_TYPE`,
`PROCESSING_CAPACITY_BUSY`, `PROCESS_INTERRUPTED`, `RESULT_EXPIRED` e
`INTERNAL_ERROR`.

## Frontera local real

El navegador usa `POST /api/v1/local/jobs` únicamente cuando el modo local está
activado explícitamente. La ruta exige un cliente loopback y `X-Local-Pilot: 1`,
no utiliza API keys, no acepta `X-Drive-File-Id`, no habilita CORS general y
reutiliza el servicio de trabajos existente. Vite sólo reenvía `/api` a
`http://127.0.0.1:8000` sin inyectar credenciales ni identificadores.

La autenticación mediante sesión `HttpOnly`, usuarios y roles queda pendiente
para la versión comercial alojada en la nube.

## Identidad y privacidad

El backend genera una identidad interna UUID por carga local. El contrato no
depende de `X-Drive-File-Id`, que pertenece a la frontera protegida de
integración con Drive y no llega al código React. El navegador tampoco recibe
API keys, secretos HMAC ni credenciales.

## Alcance deliberadamente conservado

El endpoint protegido existente permanece sin eliminar ni debilitar. El
frontend mantiene procesamiento simulado para la demostración y descargas
deshabilitadas, pero el flujo de archivo local ya envía el PDF a
`/api/v1/local/jobs`. No se conectan Drive, n8n, PostgreSQL, Redis, Docker ni
servidores desde esta entrega.

El contrato acepta sólo `budget` en esta fase. Los datos históricos de demostración pueden permanecer para probar estados, pero factura, cotización, valorización y otro documento no se ofrecen como opciones utilizables.

## Consecuencias

- Backend y TypeScript pueden validar los mismos estados, textos, campos y códigos.
- El motor no necesita cambiar para establecer la frontera web.
- Una futura integración deberá añadir autenticación del navegador y resolver la identidad interna en el servidor, sin trasladar credenciales al cliente.
