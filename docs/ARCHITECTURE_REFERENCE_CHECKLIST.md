# Checklist contra SVG de arquitectura

Referencia: `D:\CODEX\fraud_platform_architecture.svg`

El SVG define una plataforma antifraude por capas: frontend, API/autenticacion, servicios core, workers asincronos, almacenamiento, fuentes externas y seguridad transversal.

## Capa 1 - Frontend

- [x] Buscador publico con Next.js: `apps/web/src/components/search-client.tsx`.
- [x] Formulario de reporte: `apps/web/src/components/report-client.tsx`.
- [x] Evidencia asociada a reportes: backend y UI base existen.
- [x] Panel admin/revision/estados: `admin`, `cases`, `users`.
- [x] Vista de grafo con Cytoscape.js: `apps/web/src/components/graph-client.tsx`.
- [x] Analitica visual GDS conectada a `/graph`: PageRank, Degree, Louvain.

## Capa 2 - API + autenticacion

- [x] FastAPI con REST versionado: `apps/api/app/api/v1`.
- [x] Validacion Pydantic: `apps/api/app/schemas`.
- [x] Auth local JWT y roles: `apps/api/app/services/auth.py`, `core/dependencies.py`.
- [x] NextAuth / Keycloak: NextAuth habilitado con Credentials y Keycloak; API acepta JWT local y OIDC Keycloak.
- [x] Rate limit por IP con Redis: `apps/api/app/core/rate_limit.py`.

## Capa 3 - Servicios core

- [x] Motor scoring por reglas: `apps/api/app/services/scoring.py`.
- [x] Scoring con senales de grafo/casos: `case_scoring.py`.
- [x] Normalizador URLs, dominios, telefonos, correos, wallets y redes: `normalizer.py`.
- [x] Motor grafo relacional: `graph_engine.py`.
- [x] Sync PostgreSQL -> Neo4j: `neo4j_sync.py`.
- [x] Analitica Neo4j GDS: `graph_analytics.py`.
- [x] Apelaciones: `appeals.py`.
- [x] Audit log/trazabilidad: `audit.py` y escrituras en servicios sensibles.

## Capa 4 - Workers asincronos

- [x] Celery separado por colas: `apps/worker/worker/celery_app.py`.
- [x] Worker externo: URLhaus, Google Safe Browsing, VirusTotal, PhishTank y urlscan.io implementados.
- [~] Worker analisis/NLP: existe con patrones de texto simples; falta pipeline real hacia API/DB.
- [x] Worker alertas: `apps/worker/worker/services/alerts.py` envia webhook generico, Slack webhook y email SMTP.
- [x] Alertas salientes API: `notification_deliveries` procesa webhook generico, Slack webhook y email SMTP desde el outbox.
- [x] Redis como broker/cola en Docker y `.env.example`.

## Capa 5 - Almacenamiento

- [x] PostgreSQL: entidades, reportes, evidencia, casos, auditoria, notificaciones.
- [x] Neo4j: configurado en Docker, sync y GDS implementados.
- [x] MinIO/S3: evidencia soporta backend local o S3/MinIO con `EVIDENCE_STORAGE_BACKEND`.
- [x] Redis: rate limit, cache base y Celery.

## Capa 6 - Fuentes externas

- [x] VirusTotal: cliente real implementado en worker; requiere `VIRUSTOTAL_API_KEY`.
- [x] Google Safe Browsing: cliente real implementado en worker; requiere `GOOGLE_SAFE_BROWSING_API_KEY`.
- [x] PhishTank: cliente real implementado en worker; requiere `PHISHTANK_API_KEY`.
- [x] URLhaus: cliente real implementado en worker; requiere `URLHAUS_AUTH_KEY`.
- [x] urlscan.io: busqueda pasiva implementada en worker; requiere `URLSCAN_API_KEY`.

## Seguridad transversal

- [x] Input validation: Pydantic, normalizadores, content-type y size checks.
- [x] Defensa base contra SQLi: SQLAlchemy queries parametrizadas.
- [~] Defensa XSS/IDOR: hay roles y guards; falta auditoria especifica de endpoints sensibles.
- [x] EXIF stripping: `apps/api/app/services/exif.py` remueve metadata JPEG/PNG/WebP durante la subida.
- [x] Audit log: implementado.
- [x] Ley 29733: documentada y configurada en `.env.example`.

## Prioridad recomendada desde el SVG

1. Ejecutar prueba end-to-end del flujo completo y cerrar documentacion final.
