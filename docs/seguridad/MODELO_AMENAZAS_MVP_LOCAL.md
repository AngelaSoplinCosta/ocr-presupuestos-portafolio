# Riesgos del piloto OCR local

## Por qué existe este documento

Un presupuesto PDF puede contener información privada, y el OCR procesa archivos que no controlamos. Esta revisión describe la frontera local que se puede examinar en el repositorio y los límites que importan al probar el piloto con un PDF propio. No certifica que cualquier PDF sea seguro ni autoriza un despliegue público.

El recorrido web envía el archivo a FastAPI en el mismo equipo. El backend conserva el original para mostrarlo en la revisión, produce datos de observaciones y un Excel, y guarda metadatos del trabajo. El recorrido de ejemplo del frontend usa datos inventados y no hace esta carga.

## Riesgos y controles observables

| Riesgo | Qué hace esta edición | Límite pendiente | Dónde comprobarlo |
| --- | --- | --- | --- |
| Archivo que finge ser un PDF | Comprueba extensión, MIME, firma y tamaño antes de procesarlo. | Esas comprobaciones no detectan todos los PDF maliciosos; el motor OCR no está aislado en un contenedor. | `backend/app/infrastructure/storage/local.py`, `backend/tests/test_upload_security.py` |
| Escritura fuera del trabajo | Genera nombres internos, valida la ruta bajo la raíz privada y usa permisos restringidos. | La seguridad también depende de los permisos del equipo donde se ejecuta. | `backend/app/infrastructure/storage/local.py`, `backend/tests/test_upload_security.py` |
| Acceso a la API desde otra máquina | El modo local está desactivado por defecto; `backend.run_local` fija `127.0.0.1` y un worker. La ruta exige cliente loopback y `X-Local-Pilot: 1`. | La cabecera no autentica a otros procesos del mismo equipo. No abrir puertos, proxies o túneles para este piloto. | `backend/run_local.py`, `backend/app/api/middleware.py`, `backend/tests/test_local_launcher.py`, `backend/tests/test_local_jobs.py` |
| Exposición de credenciales de integración | El contrato `/v1/jobs` usa claves configuradas como hashes y HMAC; React no recibe esos secretos. | Una integración real necesita administración de secretos y revisión de acceso propia. | `backend/app/security.py`, `frontend/tests/privacy.test.tsx` |
| Uso excesivo de recursos | Limita la carga a 50 MB, acota el multipart y admite una solicitud activa. | No hay un límite de tiempo integral verificado para el OCR; un documento difícil puede mantener el proceso ocupado. | `backend/app/api/middleware.py`, `backend/tests/test_admission_and_errors.py` |
| Archivo o Excel conservado más tiempo del esperado | El PDF original, la revisión y el resultado quedan en el directorio privado del trabajo. La limpieza borra los trabajos vencidos al iniciar o ejecutar `python -m backend.app.cleanup_results`; ante error se elimina el directorio. | El vencimiento no dispara por sí solo una tarea continua. Recargar la página no borra archivos del servidor; la eliminación física puede depender del sistema de archivos. | `backend/app/services/process_job.py`, `backend/app/services/retention.py`, `backend/tests/test_retention.py` |
| Datos sensibles en registros | El logger operativo limita los campos registrados; la API devuelve códigos de error controlados. | Las salidas descargadas y los metadatos locales siguen siendo responsabilidad de quien ejecuta el piloto. | `backend/app/logging_config.py`, `backend/tests/test_security.py` |
| Dependencias vulnerables | Se fijan versiones y se pueden revisar con `npm audit` y `pip-audit`. | Una auditoría puntual no sustituye futuras revisiones de versiones ni analiza todos los binarios OCR del sistema. | `frontend/package-lock.json`, `backend/requirements.txt` |

## Uso previsto

Ejecutar únicamente en el equipo local con el lanzador indicado en `backend/README.md`; cargar sólo documentos que se tenga permiso de procesar. El recorrido de ejemplo sirve para explorar la interfaz sin un PDF. Antes de compartir un Excel, revisar los importes y la información que contiene. La ruta protegida `/v1/jobs` y las referencias a Drive son un contrato de integración separado, no una función del navegador local.
