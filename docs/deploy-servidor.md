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
docker compose -f docker-compose.prod.yml up -d --build
```

## Ver estado y logs

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f web
```

## Apagar

```bash
docker compose -f docker-compose.prod.yml down
```
