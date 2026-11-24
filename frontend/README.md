# Interfaz local para revisar presupuestos

Frontend en React, TypeScript y Vite. La interfaz conserva el nombre Quipta del prototipo visual; en este repositorio se usa para acompañar el motor OCR local: cargar un PDF propio, revisar lo extraído y descargar el Excel.

## Dos recorridos

- **Demostración:** permite explorar pantallas y decisiones con datos inventados de `src/data/demoData.ts`. No lee PDF ni genera una descarga real.
- **Procesamiento local:** envía explícitamente el PDF elegido a FastAPI, muestra revisión tabular, permite configurar columnas y ofrece un Excel y un libro técnico de trazabilidad. El recorrido es `Documento → Procesamiento → Revisión → Columnas → Excel`.

El navegador no contiene claves API, HMAC ni IDs de Drive. Las peticiones locales usan `X-Local-Pilot: 1`; el backend valida que procedan de loopback. El servidor Vite y su vista previa escuchan en `127.0.0.1`, y su proxy `/api` apunta a la API local en el puerto 8000.

## Desarrollo y comprobaciones

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
npm audit
```

Para abrir la interfaz tras configurar el backend descrito en [backend/README.md](../backend/README.md), usa `npm run dev` en esta carpeta. No expongas el servidor de desarrollo mediante `--host`, túneles o una red local compartida.

## Privacidad y límites

El ejemplo navegable usa datos inventados. Al elegir el recorrido real, el PDF se envía a la API del mismo equipo y permanece en el directorio privado del trabajo hasta la limpieza de resultados vencidos; recargar el navegador no elimina esa copia. Durante la revisión el navegador solicita el PDF local y crea una URL temporal, que revoca al cerrar el visor. No se guardan documentos en `localStorage` ni se transmiten a servicios remotos desde este cliente.

Las pruebas de interfaz usan Vitest y Testing Library. La accesibilidad se trabajó mediante controles etiquetados, navegación con teclado y mensajes de estado; siguen pendientes evaluaciones manuales con lectores de pantalla y navegadores reales.
