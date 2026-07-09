# Despliegue en Servidor

## Instalar Docker y Docker Compose en Ubuntu

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Cierra sesion y vuelve a entrar para usar `docker` sin `sudo`.

## Levantar VERIGRAPH

```bash
git clone https://github.com/NestorHuaylla/VERIGRAPH.git
cd VERIGRAPH
cp .env.production.example .env.production
nano .env.production
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

Tambien puedes usar el helper del repo, que siempre agrega `--env-file .env.production`:

```bash
chmod +x scripts/prod.sh
./scripts/prod.sh up
./scripts/prod.sh ps
```

Verifica especialmente estas variables antes de construir la web:

```env
NEXT_PUBLIC_API_URL=http://TU_IP_O_DOMINIO:8000
NEXT_PUBLIC_API_PORT=8000
NEXTAUTH_URL=http://TU_IP_O_DOMINIO:3000
CORS_ORIGINS=["http://TU_IP_O_DOMINIO:3000"]
DATABASE_URL=postgresql+asyncpg://verigraph:TU_PASSWORD@postgres:5432/verigraph
```

`NEXT_PUBLIC_API_URL` se inyecta durante el build de Next.js. Si cambias dominio, IP o puerto del API, vuelve a ejecutar:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build web
```

El contenedor API espera a PostgreSQL saludable y ejecuta `alembic upgrade head` antes de arrancar, para que `/api/v1/auth/register` tenga las tablas listas.

## Validar registro/login desde terminal

```bash
./scripts/prod.sh validate-db
./scripts/prod.sh validate-api
./scripts/prod.sh login usuario@dominio.com "password"
```

Si `validate-db` muestra `current_user = verigraph`, la conexion a PostgreSQL esta funcionando. Si el login devuelve `401`, la base y el API estan bien pero las credenciales del usuario no coinciden. Si devuelve `500`, revisa logs del API.

## Reparar password real de PostgreSQL

Si los logs del API muestran:

```text
password authentication failed for user "verigraph"
```

la password real guardada dentro del volumen de PostgreSQL no coincide con `POSTGRES_PASSWORD` / `DATABASE_URL` de `.env.production`. Esto puede pasar cuando el volumen ya existia, porque cambiar `.env.production` no actualiza automaticamente usuarios ya creados en Postgres.

Para sincronizarla:

```bash
./scripts/prod.sh sync-postgres-password
./scripts/prod.sh validate-db
```

## Ver estado y logs

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f api
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f web
```

## Carga masiva de reportes

El CSV debe tener cabeceras. Formato recomendado:

```csv
entity_type,entity_value,reason,reporter_contact
domain,ejemplo.com,Promesa de inversion garantizada vista en redes,contacto@correo.com
phone,+51999999999,Numero usado en reportes de cobro sospechoso,
```

Tambien se aceptan cabeceras en espanol: `tipo`, `valor`, `motivo`, `contacto`.

Sube el archivo al servidor dentro de `imports/`:

```bash
mkdir -p imports
```

Luego importa desde el contenedor API:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec api python -m app.scripts.import_reports_csv /imports/reportes.csv --dry-run
docker compose --env-file .env.production -f docker-compose.prod.yml exec api python -m app.scripts.import_reports_csv /imports/reportes.csv
```

## Apagar

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down
```
