# Arquitectura

VERIGRAPH sigue la arquitectura del diagrama original por capas.

## Capa 1 - Frontend

- **Buscador publico:** consulta de URL, dominio, telefono, correo, wallet o usuario.
- **Formulario:** envio de reportes y evidencia.
- **Panel admin:** revision humana, estados, casos, apelaciones y auditoria.
- **Vista de grafo:** exploracion visual de entidades conectadas con Cytoscape.js o React Flow.

## Capa 2 - API + autenticacion

- FastAPI expone endpoints REST versionados.
- Pydantic valida entrada y salida.
- Redis aplica rate limit por IP.
- La autenticacion soporta JWT local y NextAuth/Keycloak como alternativa empresarial.

## Capa 3 - Servicios core

- **Scoring:** calcula riesgo con reglas versionadas y senales del grafo.
- **Normalizador:** estandariza URLs, dominios, telefonos, correos y wallets.
- **Motor grafo:** sincroniza relaciones en Neo4j y calcula comunidades/centralidad.
- **Apelaciones:** permite corregir falsos positivos y mantener trazabilidad.

## Capa 4 - Workers asincronos

- **Worker externo:** consulta VirusTotal, Safe Browsing, PhishTank, URLhaus y urlscan.io.
- **Worker analisis:** patrones de texto, extraccion de indicadores y preparacion de analisis OCR/AI.
- **Worker alertas:** email, Slack/webhook y notificaciones internas.

## Capa 5 - Almacenamiento

- PostgreSQL: entidades, reportes, usuarios, casos, auditoria y scores.
- Neo4j: relaciones y analisis de redes.
- MinIO/S3: capturas y evidencia con backend local/S3 seleccionable.
- Redis: cache, rate limit y cola Celery.

## Capa 6 - Fuentes externas

Las fuentes externas se consultan de forma asincrona para no bloquear al usuario y para respetar cuotas.
