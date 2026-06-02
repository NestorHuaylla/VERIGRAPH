# Mapeo del diagrama SVG

Fuente canonica: `D:\CODEX\fraud_platform_architecture.svg`.

Este archivo mapea cada bloque del SVG a una ubicacion concreta dentro del repo. Para ver estado de madurez por bloque, revisar `docs/ARCHITECTURE_ALIGNMENT.md`.

## Capa 1 - Frontend

| Bloque | Carpeta |
| --- | --- |
| Buscador | `apps/web/src/app/page.tsx` |
| Formulario | `apps/web/src/app/report/page.tsx` |
| Panel admin | `apps/web/src/app/admin/page.tsx` |
| Vista de grafo / Cytoscape.js | `apps/web/src/app/graph/page.tsx`, `apps/web/package.json` |

## Capa 2 - API + autenticacion

| Bloque | Carpeta |
| --- | --- |
| Rate limit | `apps/api/app/core/rate_limit.py` |
| FastAPI | `apps/api/app/main.py` |
| Auth + roles | `apps/api/app/api/v1/endpoints/auth.py`, `apps/api/app/core/security.py`, `docker-compose.yml` opcional Keycloak |

## Capa 3 - Servicios core

| Bloque | Carpeta |
| --- | --- |
| Motor scoring | `apps/api/app/services/scoring.py` |
| Normalizador | `apps/api/app/services/normalizer.py` |
| Motor grafo | `apps/api/app/services/graph_engine.py` |
| Apelaciones + audit log | `apps/api/app/services/appeals.py`, `apps/api/app/services/audit.py`, `apps/api/app/models/audit.py` |

## Capa 4 - Workers asincronos

| Bloque | Carpeta |
| --- | --- |
| Worker externo | `apps/worker/worker/tasks/external_checks.py` |
| Worker analisis | `apps/worker/worker/tasks/analysis.py` |
| Worker alertas | `apps/worker/worker/tasks/alerts.py` |
| Redis cola | `docker-compose.yml` |

## Capa 5 - Almacenamiento

| Bloque | Configuracion |
| --- | --- |
| PostgreSQL | `docker-compose.yml`, `infra/docker/postgres/init` |
| Neo4j | `docker-compose.yml` |
| MinIO / S3 | `docker-compose.yml` |
| Redis cache | `docker-compose.yml` |

## Capa 6 - Fuentes externas

| Bloque | Carpeta |
| --- | --- |
| VirusTotal | `apps/worker/worker/services/external_sources.py` |
| Safe Browsing | `apps/worker/worker/services/external_sources.py` |
| PhishTank | `apps/worker/worker/services/external_sources.py` |
| URLhaus | `apps/worker/worker/services/external_sources.py` |
| urlscan.io | `apps/worker/worker/services/external_sources.py` |

## Seguridad transversal

| Bloque | Carpeta |
| --- | --- |
| Input validation | `apps/api/app/schemas` |
| EXIF stripping | `apps/api/app/services/exif.py`, `apps/worker/worker/services/evidence.py` |
| Audit log | `apps/api/app/models/audit.py`, `apps/api/app/services/audit.py` |
| Ley 29733 | `docs/SECURITY_AND_PRIVACY.md` |
