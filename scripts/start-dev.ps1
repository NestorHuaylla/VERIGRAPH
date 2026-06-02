param(
  [switch]$WithWorkers,
  [switch]$WithAuth,
  [switch]$NoBrowser,
  [switch]$SkipDocker,
  [switch]$ForceBuild
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

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

function Import-DotEnv {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return
  }

  foreach ($Line in Get-Content -LiteralPath $Path) {
    $Trimmed = $Line.Trim()
    if ($Trimmed.Length -eq 0 -or $Trimmed.StartsWith("#")) {
      continue
    }

    $Parts = $Trimmed.Split("=", 2)
    if ($Parts.Count -ne 2) {
      continue
    }

    $Name = $Parts[0].Trim()
    $Value = $Parts[1].Trim()
    if ($Value.StartsWith('"') -and $Value.EndsWith('"')) {
      $Value = $Value.Substring(1, $Value.Length - 2)
    }

    Set-Item -Path "Env:$Name" -Value $Value
  }
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Creado .env desde .env.example"
}

Import-DotEnv -Path ".env"

if (-not $SkipDocker) {
  Write-Host ""
  Write-Host "Levantando Docker: Postgres, Redis, Neo4j, MinIO y API..."

  $ComposeArgs = @("--profile", "app")
  $Services = @("postgres", "redis", "neo4j", "minio", "api")

  if ($WithWorkers) {
    $ComposeArgs += @("--profile", "workers")
    $Services += @("worker-external", "worker-analysis", "worker-alerts")
  }

  if ($WithAuth) {
    $ComposeArgs += @("--profile", "auth")
    $Services += @("keycloak")
  }

  $ComposeArgs += @("up", "-d")
  if ($ForceBuild) {
    $ComposeArgs += @("--build")
  }
  $ComposeArgs += $Services
  Invoke-DockerCompose -ComposeArgs $ComposeArgs
} else {
  Write-Host ""
  Write-Host "Saltando Docker. Usando los servicios que ya esten prendidos."
}

if (-not (Get-Command corepack -ErrorAction SilentlyContinue)) {
  throw "No se encontro corepack. Instala Node.js 22 o habilita corepack antes de arrancar la web."
}

if (-not (Test-Path "node_modules") -or -not (Test-Path "apps/web/node_modules")) {
  Write-Host ""
  Write-Host "Instalando dependencias de Node. Esto solo deberia pasar la primera vez..."
  & corepack pnpm install
  if ($LASTEXITCODE -ne 0) {
    throw "pnpm install fallo con codigo $LASTEXITCODE."
  }
}

if (-not $NoBrowser) {
  $OpenCommand = 'Start-Sleep -Seconds 6; Start-Process "http://localhost:3000"'
  Start-Process powershell -WindowStyle Hidden -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $OpenCommand)
}

Write-Host ""
Write-Host "Listo. Web: http://localhost:3000 | API: http://localhost:8000/docs"
Write-Host "Deja esta ventana abierta. Para parar la web: Ctrl+C."
Write-Host ""

& corepack pnpm --dir apps/web dev
