# VERIGRAPH

Plataforma local para consultar, reportar y analizar entidades con senales de fraude digital usando evidencia, scoring, grafos y revision humana.

## Capas

- **Capa 1 - Frontend:** buscador publico, formulario de reportes, panel admin y vista de grafo.
- **Capa 2 - API + autenticacion:** FastAPI, validacion Pydantic, rate limit por IP, roles, JWT local y NextAuth/Keycloak.
- **Capa 3 - Servicios core:** scoring, normalizacion, motor de grafo, apelaciones y auditoria.
- **Capa 4 - Workers asincronos:** consultas externas, analisis de texto y alertas.
- **Capa 5 - Almacenamiento:** PostgreSQL, Neo4j, MinIO/S3 y Redis.
- **Capa 6 - Fuentes externas:** VirusTotal, Safe Browsing, PhishTank, URLhaus y urlscan.io.
- **Seguridad transversal:** validacion de entrada, EXIF stripping, audit log y privacidad segun Ley 29733.

## Estructura

```txt
apps/
  web/      Next.js frontend
  api/      FastAPI REST API
  worker/   Celery workers
packages/
  shared/   taxonomias y contratos compartidos
infra/
  docker/   configuracion de servicios locales
docs/
  arquitectura, seguridad y roadmap
```

## Arranque local

Arrancar todo para desarrollo con doble click:

```txt
ARRANCAR-VERIGRAPH.bat
```

Ese arranque crea `.env` desde `.env.example` si falta, deja Docker en segundo plano para Postgres, Redis, Neo4j, MinIO y API, instala dependencias Node si no existen, y corre la web Next.js localmente con hot reload. Asi no hay que reconstruir Docker cada vez que cambias la web.

Si Docker ya quedo prendido y solo quieres abrir la web:

```txt
SOLO-WEB-VERIGRAPH.bat
```

Si cambiaste backend, dependencias Python o Dockerfiles y necesitas reconstruir:

```txt
RECONSTRUIR-VERIGRAPH.bat
```

Tambien se puede ejecutar desde terminal:

```powershell
pnpm dev
```

Para apagar los contenedores de Docker:

```txt
APAGAR-DOCKER-VERIGRAPH.bat
```

## Arranque manual

Levantar solo infraestructura:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -InfraOnly
```

Levantar todo dentro de Docker:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Full
```

## Primer admin

El registro publico crea usuarios `reporter`. Para crear el primer usuario admin usa un comando local desde `apps/api`:

```powershell
python -m app.scripts.create_admin --email admin@verigraph.local --password "cambia-esta-password"
```

## Auth empresarial opcional

El login local sigue disponible en `/login`. Para habilitar Keycloak/NextAuth:

```env
KEYCLOAK_ISSUER=http://localhost:8080/realms/verigraph
KEYCLOAK_CLIENT_ID=verigraph-web
KEYCLOAK_CLIENT_SECRET=...
KEYCLOAK_AUTO_PROVISION_USERS=true
NEXT_PUBLIC_KEYCLOAK_ENABLED=true
```

Los roles aceptados son `admin`, `analyst`, `legal` y `reporter`; tambien se aceptan con prefijo `verigraph_`.

## Evidencia

Por defecto la evidencia se guarda localmente. Para usar MinIO/S3:

```env
EVIDENCE_STORAGE_BACKEND=s3
S3_ENDPOINT=http://minio:9000
S3_BUCKET_EVIDENCE=verigraph-evidence
S3_ACCESS_KEY=verigraph
S3_SECRET_KEY=verigraph-local
```

Las imagenes JPEG, PNG y WebP se limpian de metadata durante el upload antes de calcular `sha256`.

## Puertos locales

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Keycloak opcional: http://localhost:8080
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- Neo4j Browser: http://localhost:7474
- MinIO console: http://localhost:9001

## Probar desde celular en la misma red

1. Levanta el API en un host accesible:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Full
```

2. Levanta el frontend. El script escucha en `0.0.0.0`, no solo en `localhost`:

```powershell
corepack pnpm --dir apps/web dev
```

3. En el celular abre `http://IP-DE-TU-PC:3000`.

Cuando la web se abre desde un celular, el frontend cambia automaticamente las llamadas del API desde `localhost:8000` hacia `IP-DE-TU-PC:8000`. El API permite origenes de red local como `10.x.x.x`, `172.16-31.x.x` y `192.168.x.x`.

## Produccion en servidor Linux

1. Crear el archivo de entorno:

```bash
cp .env.production.example .env.production
```

2. Editar `.env.production` con la IP/dominio real y secretos reales. Como minimo, cambiar:

```env
PUBLIC_WEB_URL=http://TU_IP_O_DOMINIO:3000
PUBLIC_API_URL=http://TU_IP_O_DOMINIO:8000
NEXT_PUBLIC_API_URL=http://TU_IP_O_DOMINIO:8000
NEXTAUTH_URL=http://TU_IP_O_DOMINIO:3000
CORS_ORIGINS=["http://TU_IP_O_DOMINIO:3000"]
POSTGRES_PASSWORD=...
DATABASE_URL=postgresql+asyncpg://verigraph:...@postgres:5432/verigraph
JWT_SECRET=...
NEXTAUTH_SECRET=...
WORKER_API_TOKEN=...
NEO4J_PASSWORD=...
MINIO_ROOT_PASSWORD=...
S3_SECRET_KEY=...
```

3. Levantar siempre con `--env-file .env.production`. Si no se usa `--env-file`, Compose puede mostrar warnings de variables vacias aunque los contenedores tengan `env_file`.

```bash
sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Tambien se puede usar el helper:

```bash
chmod +x scripts/prod.sh
sudo ./scripts/prod.sh up
sudo ./scripts/prod.sh ps
```

4. Validar base de datos, migraciones y API:

```bash
sudo ./scripts/prod.sh validate-db
sudo ./scripts/prod.sh validate-api
```

Debe aparecer `current_user = verigraph` y la lista de tablas debe incluir `users`, `reports`, `risk_rules` y `risk_scores`.

5. Probar login desde terminal:

```bash
sudo ./scripts/prod.sh login usuario@dominio.com "password"
```

Si sale `200 OK`, auth funciona. Si sale `401 Unauthorized`, el API y la DB estan bien pero el usuario/password no coinciden. Si sale `500`, revisar:

```bash
sudo ./scripts/prod.sh logs-api 120
```

### Reparar password real de PostgreSQL

Si los logs muestran:

```text
password authentication failed for user "verigraph"
```

significa que `DATABASE_URL` y la password real del usuario `verigraph` dentro del volumen de Postgres no coinciden. Esto pasa cuando el volumen ya existia: cambiar `.env.production` no cambia automaticamente la password interna.

Para sincronizar la password real con `POSTGRES_PASSWORD` de `.env.production`:

```bash
sudo ./scripts/prod.sh sync-postgres-password
```

Luego validar:

```bash
sudo ./scripts/prod.sh validate-db
sudo ./scripts/prod.sh restart api
```
