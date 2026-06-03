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
