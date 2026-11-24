# API de orquestación OCR

Integración vertical síncrona entre un cliente autorizado y el motor local. La solicitud
HTTP permanece abierta hasta obtener `COMPLETADO`, `REVISAR` o `ERROR`.

## Seguridad relevante

- El tenant procede exclusivamente del token `X-API-Key` autenticado.
- Los tokens se configuran como hashes scrypt; nunca se persisten en claro.
- El ID de Drive se transforma con HMAC-SHA-256 antes de persistirse.
- Cada trabajo usa `OCR_JOB_STORAGE_ROOT/<uuid>/` y nombres físicos internos.
- El logger del motor se silencia temporalmente y se restaura al terminar.
- Los logs operativos contienen sólo `job_id`, estado, duración y códigos seguros.
- Un bloqueo en memoria serializa el motor y se libera siempre mediante `finally`.
- La frontera ASGI autentica y valida `Content-Length` antes de que FastAPI analice
  el multipart.
- Sólo se admite un POST activo; una segunda creación recibe `503` sin consumir el
  documento.

SQLite es únicamente una alternativa local y de pruebas. Producción debe usar
PostgreSQL, migraciones Alembic y almacenamiento durable.

## Límite de concurrencia del MVP

Esta versión debe ejecutarse con una instancia de API, un worker de Uvicorn y un
solo documento en procesamiento. El bloqueo es local al proceso: no coordina
réplicas ni varios workers. Una futura ampliación deberá usar un bloqueo distribuido
respaldado por PostgreSQL antes de aumentar réplicas.

Al iniciar esta única instancia, cualquier trabajo que hubiera quedado en
`PROCESANDO` se marca `ERROR` con `PROCESS_INTERRUPTED`. Un nuevo envío explícito
del mismo PDF puede reutilizar ese trabajo e incrementar `attempt_count`; nunca se
reanuda sin una carga nueva. Esta recuperación no es válida con dos instancias
simultáneas.

Un trabajo que hubiera quedado en `RECIBIDO` antes de invocar el motor tampoco se
reanuda por sí solo: una carga explícita idéntica reemplaza de forma controlada la
entrada provisional y comienza su primer intento.

Un trabajo existente en `PROCESANDO` se devuelve sin volver a invocar el motor. Un
trabajo en `ERROR` es terminal y no se reintenta automáticamente con el mismo
contenido; se requiere intervención administrativa o contenido nuevo en Drive.

La restricción única evita duplicados de la misma identidad. En PostgreSQL, la
creación de una versión nueva se serializa adicionalmente con un advisory lock
transaccional derivado del identificador HMAC. SQLite no demuestra esa propiedad
de concurrencia y se limita a pruebas locales.

## Probar la interfaz con un PDF propio

Desde la raíz, con Python 3.12 y las herramientas OCR del sistema instaladas cuando el PDF sea escaneado:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
export OCR_LOCAL_MODE_ENABLED=true
export OCR_ID_HMAC_SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export OCR_API_TOKEN_HASHES_JSON="$(.venv/bin/python - <<'PY'
import json
import secrets
from backend.app.security import hash_api_token
print(json.dumps([{"tenant_id": "unused-local", "token_hash": hash_api_token(secrets.token_urlsafe(32))}]))
PY
)"
.venv/bin/alembic -c backend/alembic.ini upgrade head
.venv/bin/python -m backend.run_local
```

En otra terminal, inicia el cliente con `cd frontend && npm ci && npm run dev`. Abre la dirección local que muestre Vite, elige el recorrido de procesamiento local, carga tu propio PDF, revisa las partidas y descarga el Excel. El modo demostrativo usa datos ficticios y no procesa el archivo. Estos valores de entorno se generan para una sesión local; no los agregues al repositorio. La ruta `/v1/jobs` requiere una configuración de autenticación separada si se utiliza en una integración.

## Configuración y admisión

Las variables están definidas en `app/config.py`. La aplicación no carga archivos
`.env` automáticamente. Los secretos deben inyectarse desde el entorno o desde un
gestor de secretos.

`OCR_MAX_REQUEST_BYTES` limita la solicitud multipart completa y debe ser mayor
que `OCR_MAX_UPLOAD_BYTES`. El proxy de producción debe imponer el mismo límite
antes de FastAPI; el control interno no reemplaza al proxy. Los POST sin
`Content-Length` se rechazan. El MVP exige `OCR_MAX_ACTIVE_REQUESTS=1`.

`OCR_DOCS_ENABLED=false` desactiva `/docs`, `/redoc` y `/openapi.json` en el
entorno desplegado.

La API expone:

- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/result`
- `POST /api/v1/local/jobs` cuando `OCR_LOCAL_MODE_ENABLED=true` y el cliente es loopback
- `GET /health/live`
- `GET /health/ready`

`POST /v1/jobs` requiere `X-API-Key`, `X-Drive-File-Id`, opcionalmente
`X-Drive-Revision`, y un campo multipart `file`.

La ruta local del piloto no utiliza API key ni `X-Drive-File-Id`. Requiere
`X-Local-Pilot: 1`, cliente loopback, modo local activado explícitamente y los
campos multipart `file` y `document_type=budget`. El backend genera la identidad
interna del archivo. Esta ruta no habilita CORS y no sustituye la autenticación
de `/v1/jobs`.

Para el uso local explícito, con `OCR_LOCAL_MODE_ENABLED=true`, el launcher fijo
se invoca desde la raíz con `python -m backend.run_local`. No acepta parámetros
para cambiar host o workers: usa `127.0.0.1`, puerto `8000` y un solo worker.

`live` sólo confirma que el proceso responde. `ready` comprueba configuración,
conectividad y columnas requeridas de la base, escritura del almacenamiento y el
contrato estático del adaptador, sin ejecutar OCR.

## Retención

Al completar o marcar para revisión se eliminan el PDF de entrada y derivados de
trabajo; el XLSX permanece durante `OCR_RESULT_RETENTION_HOURS`. Ante error se
elimina todo el directorio del trabajo. `unlink` es una eliminación de mejor
esfuerzo: en almacenamiento cifrado o copy-on-write no garantiza borrado físico.

La limpieza se ejecuta una vez al iniciar y también está disponible como comando
administrativo independiente:

```bash
python -m backend.app.cleanup_results
```

En un despliegue futuro debe invocarse mediante cron o una tarea administrada
externa. No se ejecuta dentro del camino crítico de una solicitud. Los fallos de
retención quedan aislados y sólo registran cantidades y códigos seguros.

Si un resultado ya venció o desapareció, el estado informa
`result_available=false` y `error_code=RESULT_EXPIRED`. El mismo contenido sólo se
regenera cuando vuelve a proporcionarse explícitamente el PDF; el intento se suma
al registro existente.

## Inicio y migraciones

Antes de admitir tráfico debe aplicarse `alembic upgrade head`. Readiness rechaza
un esquema sin las columnas requeridas, pero no ejecuta migraciones. La migración
inicial incorpora `processing_started_at`, `attempt_count` y restricciones `CHECK`
para estados, hashes e intentos.

No existe todavía una imagen desplegable. Esta edición está diseñada para uso local.
