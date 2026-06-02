# Checklist E2E MVP

Objetivo: validar el flujo completo de VERIGRAPH con servicios locales Docker, API, frontend y workers.

## Preparacion

1. Copiar `.env.example` a `.env` y configurar al menos:
   - `JWT_SECRET`
   - `WORKER_API_TOKEN`
   - `URLHAUS_AUTH_KEY`
   - `GOOGLE_SAFE_BROWSING_API_KEY`
   - opcional: `VIRUSTOTAL_API_KEY`, `PHISHTANK_API_KEY`, `URLSCAN_API_KEY`
2. Levantar infraestructura:

```powershell
docker compose up -d postgres redis neo4j minio
```

3. Ejecutar migraciones:

```powershell
cd D:\CODEX\VERIGRAPH\apps\api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
```

4. Crear admin:

```powershell
cd D:\CODEX\VERIGRAPH\apps\api
..\..\.venv\Scripts\python.exe -m app.scripts.create_admin --email admin@verigraph.local --password "cambia-esta-password"
```

## Flujo Funcional

1. Crear reporte publico desde `/report`.
2. Subir evidencia desde el formulario o desde el panel admin.
3. Confirmar metadata de evidencia:
   - `storage_status=stored`
   - `storage_backend=local` o `s3`
   - `exif.status` para imagenes.
4. Ejecutar analisis de evidencia desde panel admin.
5. Ejecutar reputacion externa con worker o llamada directa.
6. Confirmar checks persistidos en:
   - `GET /api/v1/entities/{entity_id}/external-reputation`
7. Confirmar que el score publico incorpora senales externas:
   - `GET /api/v1/entities/risk?value=...`
8. Crear o sincronizar expediente desde la entidad.
9. Abrir `/graph` y confirmar preview de grafo.
10. Ejecutar sync Neo4j:

```http
POST /api/v1/graph/sync/neo4j?batch_size=500
```

11. Ejecutar GDS:
   - PageRank
   - Degree
   - Louvain
12. Confirmar alertas:
   - notificacion creada.
   - delivery pendiente/enviado/fallido visible en `/dashboard`.
13. Revisar auditoria del reporte.

## Validacion Tecnica

```powershell
cd D:\CODEX\VERIGRAPH\apps\api
..\..\.venv\Scripts\python.exe -m pytest tests

cd D:\CODEX\VERIGRAPH\apps\worker
..\..\.venv\Scripts\python.exe -m pytest tests

cd D:\CODEX\VERIGRAPH
corepack pnpm --dir apps\web typecheck
corepack pnpm --dir apps\web build
powershell -ExecutionPolicy Bypass -File .\scripts\check-architecture.ps1
```

## Criterio De Cierre

- API tests completos pasan.
- Worker tests completos pasan.
- Frontend typecheck/build pasa.
- Architecture check pasa.
- El flujo crea reporte, evidencia, checks externos, score actualizado, expediente, grafo, alerta y auditoria.
