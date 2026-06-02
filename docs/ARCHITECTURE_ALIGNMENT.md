# Alineacion con `fraud_platform_architecture.svg`

Fuente de referencia: `D:\CODEX\fraud_platform_architecture.svg`.

Este documento usa el SVG como estructura canonica del proyecto. Si se agrega, mueve o elimina una pieza de VERIGRAPH, debe conservarse la correspondencia con estas capas.

## Estado general

La estructura del repositorio coincide con el SVG a nivel de capas, carpetas y puntos de entrada. Los bloques principales del MVP tecnico ya tienen implementacion funcional; las brechas restantes son validacion end-to-end, endurecimiento de seguridad puntual y preparacion operacional.

## Matriz por capa

| Capa SVG | Bloque | Ubicacion en repo | Estado |
| --- | --- | --- | --- |
| Capa 1 - Frontend | Buscador / Next.js publico | `apps/web/src/app/page.tsx`, `apps/web/src/components/search-client.tsx` | Implementado |
| Capa 1 - Frontend | Formulario / reporte + evidencia | `apps/web/src/app/report/page.tsx`, `apps/web/src/components/report-client.tsx` | Implementado |
| Capa 1 - Frontend | Panel admin / revision y estados | `apps/web/src/app/admin/page.tsx`, `apps/web/src/components/admin-client.tsx` | Implementado con fallback demo en desarrollo |
| Capa 1 - Frontend | Vista de grafo / Cytoscape.js | `apps/web/src/app/graph/page.tsx`, `apps/web/src/components/graph-client.tsx`, `apps/web/package.json` | Implementado |
| Capa 2 - API + autenticacion | FastAPI / REST / Pydantic | `apps/api/app/main.py`, `apps/api/app/schemas` | Presente |
| Capa 2 - API + autenticacion | Auth + roles / NextAuth / Keycloak | `apps/web/src/lib/auth-options.ts`, `apps/web/src/app/api/auth/[...nextauth]/route.ts`, `apps/api/app/core/security.py`, `docker-compose.yml` | Implementado |
| Capa 2 - API + autenticacion | Rate limit / Redis por IP | `apps/api/app/core/rate_limit.py`, `docker-compose.yml` | Presente |
| Capa 3 - Servicios core | Motor scoring / reglas + grafo | `apps/api/app/services/scoring.py`, `apps/api/app/services/case_scoring.py` | Implementado |
| Capa 3 - Servicios core | Normalizador / URLs, phones, wallets | `apps/api/app/services/normalizer.py` | Implementado |
| Capa 3 - Servicios core | Motor grafo / Neo4j / Louvain | `apps/api/app/services/graph_engine.py`, `apps/api/app/services/neo4j_sync.py`, `apps/api/app/services/graph_analytics.py`, `docker-compose.yml` | Implementado |
| Capa 3 - Servicios core | Apelaciones / audit log / trazabilidad | `apps/api/app/services/appeals.py`, `apps/api/app/services/audit.py`, `apps/api/app/models/audit.py` | Implementado |
| Capa 4 - Workers asincronos | Worker externo / Celery / consultas APIs | `apps/worker/worker/tasks/external_checks.py`, `apps/worker/worker/services/external_sources.py` | Implementado |
| Capa 4 - Workers asincronos | Worker analisis / NLP / patrones texto | `apps/worker/worker/tasks/analysis.py`, `apps/worker/worker/services/text_patterns.py` | Presente inicial |
| Capa 4 - Workers asincronos | Worker alertas / Email / Slack webhook | `apps/worker/worker/tasks/alerts.py`, `apps/worker/worker/services/alerts.py` | Implementado |
| Capa 4 - Workers asincronos | Redis / cola | `apps/worker/worker/celery_app.py`, `docker-compose.yml` | Presente |
| Capa 5 - Almacenamiento | PostgreSQL / entidades / reportes | `docker-compose.yml`, `apps/api/app/models`, `apps/api/app/migrations` | Implementado con migraciones Alembic |
| Capa 5 - Almacenamiento | Neo4j / grafo de relaciones | `docker-compose.yml`, `apps/api/app/services/neo4j_sync.py`, `apps/api/app/services/graph_analytics.py` | Implementado |
| Capa 5 - Almacenamiento | MinIO / S3 / capturas / evidencia | `docker-compose.yml`, `apps/api/app/services/storage.py`, `apps/api/app/models/evidence.py` | Implementado con backend local/S3 |
| Capa 5 - Almacenamiento | Redis / cache | `docker-compose.yml`, `apps/api/app/core/rate_limit.py` | Presente |
| Capa 6 - Fuentes externas | VirusTotal | `packages/shared/external_sources.json`, `apps/worker/worker/services/external_sources.py` | Implementado |
| Capa 6 - Fuentes externas | Safe Browsing | `packages/shared/external_sources.json`, `apps/worker/worker/services/external_sources.py` | Implementado |
| Capa 6 - Fuentes externas | PhishTank | `packages/shared/external_sources.json`, `apps/worker/worker/services/external_sources.py` | Implementado |
| Capa 6 - Fuentes externas | URLhaus | `packages/shared/external_sources.json`, `apps/worker/worker/services/external_sources.py` | Implementado |
| Capa 6 - Fuentes externas | urlscan.io | `packages/shared/external_sources.json`, `apps/worker/worker/services/external_sources.py` | Implementado |
| Seguridad transversal | Input validation / XSS / SQLi / IDOR | `apps/api/app/schemas`, `packages/shared/security_controls.json` | Parcial |
| Seguridad transversal | EXIF stripping / privacidad reportante | `apps/api/app/services/exif.py`, `apps/api/app/services/storage.py` | Implementado durante upload |
| Seguridad transversal | Audit log / trazabilidad acciones | `apps/api/app/models/audit.py`, `apps/api/app/services/audit.py` | Implementado |
| Seguridad transversal | Ley 29733 / datos personales PE | `docs/SECURITY_AND_PRIVACY.md` | Documentado |

## Brechas que no debe ocultar la estructura

- El SVG ya esta cubierto por carpetas, servicios y dependencias principales.
- El MVP necesita una prueba end-to-end con servicios Docker levantados y datos reales de integracion.
- El worker de analisis conserva OCR/AI como stubs controlados; el analisis de texto plano y extraccion de indicadores ya esta operativo.
- La proteccion legal fuerte antes de produccion requiere politica operacional de retencion/eliminacion y revision legal final.
- Falta endurecimiento especifico de XSS/IDOR sobre endpoints sensibles antes de exposicion publica amplia.

## Verificacion

Ejecutar desde la raiz del repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-architecture.ps1
```

El script valida que las piezas estructurales exigidas por el SVG existan y que algunas dependencias/servicios clave esten declarados.
