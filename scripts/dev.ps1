param(
  [switch]$InfraOnly,
  [switch]$Auth,
  [switch]$Full
)

$ErrorActionPreference = "Stop"

function Invoke-DockerCompose {
  param([string[]]$ComposeArgs)

  if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    & docker-compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
      throw "Docker Compose fallo con codigo $LASTEXITCODE."
    }
    return
  }

  if (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
      throw "Docker Compose fallo con codigo $LASTEXITCODE."
    }
    return
  }

  throw "No se encontro Docker Compose. Instala Docker Desktop o agrega Docker Compose al PATH."
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Creado .env desde .env.example"
}

if ($InfraOnly) {
  Invoke-DockerCompose -ComposeArgs @("up", "-d", "postgres", "redis", "neo4j", "minio")
  exit 0
}

if ($Auth) {
  Invoke-DockerCompose -ComposeArgs @("--profile", "auth", "up", "-d", "keycloak")
  exit 0
}

if ($Full) {
  Invoke-DockerCompose -ComposeArgs @("--profile", "app", "--profile", "workers", "up", "--build")
  exit 0
}

Write-Host "Uso:"
Write-Host "  ./scripts/dev.ps1 -InfraOnly"
Write-Host "  ./scripts/dev.ps1 -Auth"
Write-Host "  ./scripts/dev.ps1 -Full"
