# Modelo de amenazas del MVP local

## Alcance y límites

Este modelo cubre la primera fase de integración web local entre el frontend y la API de orquestación. No se ejecuta OCR ni se procesan documentos como parte de esta revisión. El modelo protege el PDF de entrada, los metadatos del trabajo, el resultado XLSX y los registros operativos.

El modo local se considera un entorno de desarrollo controlado, no un despliegue público. Los estados de control usados en este documento son explícitos:

- **IMPLEMENTADO:** existe una defensa en el código o en la configuración.
- **VERIFICADO:** la defensa implementada tiene una prueba automatizada o una comprobación reproducible en esta fase.
- **PENDIENTE ANTES DE NUBE:** no se debe desplegar fuera del equipo local hasta implementar y verificar el control indicado.

Un control puede estar simultáneamente **IMPLEMENTADO** y **VERIFICADO**. **PARCIAL** sólo indica que una parte local existe y otra parte permanece **PENDIENTE ANTES DE NUBE**.

## Activos y límites de confianza

- PDF original y su contenido potencialmente sensible.
- Identidad del tenant, identificador de Drive y revisión del documento.
- Directorio privado de cada trabajo y resultado XLSX.
- Credenciales de API y secreto HMAC.
- Base de datos, logs y configuración del proceso.
- Navegador: el React del MVP no debe recibir ni persistir API keys o secretos.

La frontera de entrada es HTTP multipart. El cliente no es confiable: nombre, MIME, tamaño y bytes del archivo se validan en el servidor. El contenido del PDF tampoco es confiable y no debe interpretarse durante esta fase.

## Amenazas mínimas y tratamiento

| ID | Amenaza | Impacto | Control exigido | Estado en esta fase | Evidencia o prueba |
| --- | --- | --- | --- | --- | --- |
| T01 | PDF falso o malicioso | Ejecución o consumo inesperado al abrir/procesar un archivo | Validar extensión, MIME, firma, tamaño y conservar el original fuera del directorio público; antimalware antes de nube | PARCIAL: IMPLEMENTADO y VERIFICADO en la frontera; PENDIENTE ANTES DE NUBE el antimalware | `backend/tests/test_upload_security.py` |
| T02 | Path traversal y symlinks | Escritura, lectura o borrado fuera del área del trabajo | Generar nombres internos, bloquear rutas absolutas y `../`, resolver y comprobar rutas, rechazar symlinks | IMPLEMENTADO y VERIFICADO | `backend/tests/test_upload_security.py` |
| T03 | Exposición de credenciales | Acceso no autorizado a trabajos o infraestructura | API keys sólo como hashes scrypt, secreto HMAC fuera del código, sin secretos en React | PARCIAL: IMPLEMENTADO y VERIFICADO para API/frontend; PENDIENTE ANTES DE NUBE el gestor de secretos | `backend/tests/test_security.py` y `frontend/tests/privacy.test.tsx` |
| T04 | Acceso cruzado entre empresas | Lectura o sustitución de documentos de otro tenant | Tenant derivado exclusivamente de la API key, HMAC del ID de Drive y autorización por tenant en repositorio | IMPLEMENTADO y VERIFICADO | `backend/tests/test_tenant_isolation.py` y `backend/tests/test_security.py` |
| T05 | Consumo excesivo de CPU, memoria y almacenamiento | Denegación de servicio o agotamiento del equipo | PDF máximo de 50 MB, límite multipart mayor pero acotado, chunks, timeout y una sola ejecución simultánea | PARCIAL: tamaño/chunks/concurrencia IMPLEMENTADOS y VERIFICADOS; PENDIENTE ANTES DE NUBE el timeout | `backend/tests/test_upload_security.py`, `backend/tests/test_admission_and_errors.py` |
| T06 | Información sensible en logs | Filtración de documentos, rutas, nombres o credenciales | Logs sólo con campos seguros: IDs UUID, estado, duración, códigos y métricas acotadas | IMPLEMENTADO y VERIFICADO | `backend/tests/test_security.py` y `backend/app/logging_config.py` |
| T07 | Conservación excesiva | Incumplimiento de privacidad o aumento del impacto de una filtración | Eliminar entrada y temporales al completar/error; retener XLSX sólo durante el plazo configurado | IMPLEMENTADO y VERIFICADO para la política local | `backend/tests/test_retention.py` |
| T08 | Manipulación o sustitución de resultados | Descarga de un resultado incorrecto o alterado | Nombre físico interno, rutas privadas, hash SHA-256 de entrada y resultado, transición de estados y autorización por tenant | PARCIAL: hash de entrada/transiciones IMPLEMENTADOS y VERIFICADOS; PENDIENTE ANTES DE NUBE el hash verificable del resultado | `backend/tests/test_processing_states.py` y `backend/tests/test_result.py` |
| T09 | Dependencias vulnerables | Compromiso de la cadena de suministro | Versiones fijadas, revisión de dependencias antes de cada entrega y auditoría en CI | PARCIAL: versiones fijadas IMPLEMENTADAS y auditoría local VERIFICADA; PENDIENTE ANTES DE NUBE auditoría CI | `frontend/package-lock.json`, requirements del proyecto |
| T10 | Exposición accidental del modo local a Internet | Acceso remoto no autorizado a la API local | Modo local desactivado por defecto, escucha exclusiva en `127.0.0.1`, sin exposición mediante proxy o túnel | PENDIENTE ANTES DE NUBE de implementación y verificación | Configuración del servidor y prueba de despliegue |

## Requisitos verificables de aceptación

- **R01. Modo local:** desactivado por defecto; habilitación explícita sólo para desarrollo.
- **R02. Red:** la API local escucha exclusivamente en `127.0.0.1`; no se acepta `0.0.0.0` por defecto.
- **R03. Tamaño:** se rechaza cualquier PDF mayor de 50 MB y la solicitud multipart completa también tiene un límite superior acotado.
- **R04. Tipo:** se valida extensión `.pdf`, MIME `application/pdf` y firma `%PDF-`; ninguna validación depende sólo del nombre.
- **R05. Nombres:** el nombre físico se genera internamente (`source.pdf`, `result.xlsx`); nunca se usa el nombre del cliente como ruta.
- **R06. Rutas:** se bloquean rutas absolutas, `../`, separadores no permitidos y symlinks; la ruta resuelta debe permanecer bajo la raíz privada.
- **R07. Almacenamiento:** entradas, temporales y resultados viven fuera de cualquier directorio público o servido por el frontend.
- **R08. Permisos:** raíz y directorios de trabajo usan `0700`; archivos usan `0600`; la aplicación no requiere privilegios elevados.
- **R09. Recursos:** existe timeout de procesamiento, chunks acotados y una sola ejecución simultánea en el MVP local.
- **R10. Errores:** las respuestas no revelan rutas, trazas, nombres documentales, credenciales ni detalles del motor; sólo exponen códigos sanitizados y `request_id`.
- **R11. Integridad:** se calcula y persiste SHA-256 de la entrada y se calcula SHA-256 verificable del resultado antes de entregarlo.
- **R12. Retención:** se documenta el plazo del resultado, se eliminan entrada y temporales al terminar y se elimina todo ante error; la eliminación se verifica operativamente.
- **R13. Frontend:** React no contiene API keys, secretos HMAC, credenciales, tokens ni valores equivalentes; tampoco los persiste en almacenamiento del navegador.

En esta revisión son pruebas automatizadas sin OCR R03, R04, R05, R06, R07, R08, R10, R13 y partes de R09/R11. R01, R02, timeout y hash del resultado requieren una implementación de arranque/procesamiento que queda fuera de esta fase.

## Controles previos a nube

Antes de conectar almacenamiento o ejecución en nube deben implementarse y verificarse, como mínimo:

- HTTPS con validación y rotación de certificados.
- Sesiones `HttpOnly`, `Secure` y `SameSite` cuando exista sesión web.
- Protección CSRF para operaciones autenticadas basadas en cookies.
- MFA para operadores y cuentas administrativas.
- RBAC con mínimo privilegio y separación entre tenants y operadores.
- Cifrado en tránsito y en reposo, incluida la base de datos y los objetos.
- Gestor de secretos; ningún secreto en Git, React, imágenes o logs.
- Antimalware y cuarentena del PDF antes de ponerlo a disposición del OCR.
- Rate limiting por identidad, tenant y origen, además de límites de tamaño.
- Aislamiento del OCR en proceso/contendor sin privilegios, con filesystem y red restringidos.
- Monitoreo de admisión, errores, recursos, integridad y retención, sin registrar contenido documental.
- Procedimiento de respuesta a incidentes: detección, contención, preservación de evidencia, comunicación, recuperación y rotación de credenciales.

## Decisiones explícitas de esta fase

No se instala ClamAV ni ninguna herramienta nueva de seguridad. No se ejecuta OCR, no se abre el PDF como documento y no se modifica el adaptador del motor. Las pruebas usan bytes sintéticos mínimos únicamente para verificar la frontera de carga y el almacenamiento.
