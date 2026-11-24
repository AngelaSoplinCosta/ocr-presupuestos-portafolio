# Cliente local de Quipta

Frontend en React, TypeScript y Vite para un piloto de extracción de presupuestos.

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

Los datos del modo demostrativo son sintéticos. Un PDF real se envía al backend local al pulsar continuar y puede mostrarse temporalmente mediante una URL de objeto del navegador durante la revisión. Las URLs temporales se revocan cuando ya no hacen falta. No se guardan documentos en `localStorage` ni se transmiten a un servicio remoto desde este cliente.

Las pruebas de interfaz usan Vitest y Testing Library. La accesibilidad se trabajó mediante controles etiquetados, navegación con teclado y mensajes de estado; siguen pendientes evaluaciones manuales con lectores de pantalla y navegadores reales.
