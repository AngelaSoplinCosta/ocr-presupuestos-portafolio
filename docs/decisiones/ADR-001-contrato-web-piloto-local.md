# ADR-001: contrato web del piloto local

- Estado: decisión de diseño del piloto local, actualizada para el recorrido de carga y exportación.
- Fecha inicial: 2026-08-20.
- Alcance: contrato de datos entre el navegador y la API local.

## Motivo

El motor ya podía trabajar con un PDF propio desde Python. Para revisar partidas en el navegador hacía falta una ruta local que recibiera el archivo sin colocar credenciales de integración en React. El recorrido de ejemplo se mantiene separado: enseña la interfaz, pero no procesa ni descarga un documento.

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

Esta cabecera identifica el recorrido local; no es autenticación para exponer la API a una red. El lanzador `backend.run_local` fija host `127.0.0.1` y un worker. No se ha preparado este sistema para acceso remoto.

## Identidad y privacidad

El backend genera una identidad interna UUID por carga local. El contrato no
depende de `X-Drive-File-Id`, que pertenece a la frontera protegida de
integración con Drive y no llega al código React. El navegador tampoco recibe
API keys, secretos HMAC ni credenciales.

## Alcance del recorrido

El endpoint protegido `/v1/jobs` es una frontera distinta para integración autenticada. El flujo local envía el PDF a `/api/v1/local/jobs`, espera el resultado, presenta una revisión tabular y permite descargar el Excel. El ejemplo visual conserva procesamiento simulado y descargas deshabilitadas. No se conecta Drive ni se despliega un servidor remoto desde este recorrido.

El PDF se conserva en el almacenamiento privado del trabajo para mostrarlo durante la revisión. La limpieza de resultados vencidos se ejecuta al iniciar la API o con el comando de mantenimiento; recargar el navegador no lo elimina.

El contrato acepta sólo `budget` en esta fase. Los datos históricos de demostración pueden permanecer para probar estados, pero factura, cotización, valorización y otro documento no se ofrecen como opciones utilizables.

## Consecuencias

- Backend y TypeScript pueden validar los mismos estados, textos, campos y códigos.
- El motor no necesita cambiar para establecer la frontera web.
- Si alguna vez se ofrece acceso remoto, hará falta diseñar y probar autenticación del navegador y controles de aislamiento; el encabezado local no basta.
