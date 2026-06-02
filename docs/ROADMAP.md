# Roadmap

## Fase 1 - Base local

- Docker local con PostgreSQL, Redis, Neo4j y MinIO.
- API FastAPI con healthcheck y routers base.
- Frontend Next.js con pantallas base.
- Workers Celery separados por cola.
- Modelo inicial de entidades, reportes, evidencia, casos y auditoria.

## Fase 2 - MVP funcional

- [x] Auth local con roles.
- [x] Crear reportes con evidencia.
- [x] Consultar entidades.
- [x] Scoring por reglas y senales externas.
- [x] Panel admin con estados, evidencia, apelaciones y casos.
- [x] Grafo visual con Cytoscape.

## Fase 3 - Analisis avanzado

- [x] Integraciones externas: URLhaus, Google Safe Browsing, VirusTotal, PhishTank y urlscan.io.
- [x] Deteccion de patrones de texto plano y extraccion de indicadores.
- [x] Comunidades, PageRank y Degree en Neo4j GDS.
- [x] Alertas internas y salientes por webhook/Slack/email.
- [ ] Exportacion PDF/CSV.

## Fase 4 - Producto escalable

- [x] Keycloak o proveedor IAM via NextAuth/OIDC.
- [ ] Observabilidad.
- [ ] Deploy cloud.
- [ ] API privada para empresas.
- [ ] Extension de navegador.
