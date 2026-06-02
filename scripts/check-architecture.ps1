$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$missing = New-Object System.Collections.Generic.List[string]

function Test-ProjectPath {
    param(
        [string]$Name,
        [string]$RelativePath
    )

    $fullPath = Join-Path $repoRoot $RelativePath
    if (Test-Path $fullPath) {
        Write-Host "[OK] $Name -> $RelativePath"
        return
    }

    Write-Host "[MISSING] $Name -> $RelativePath"
    $missing.Add($Name)
}

function Test-ProjectPattern {
    param(
        [string]$Name,
        [string]$RelativePath,
        [string]$Pattern
    )

    $fullPath = Join-Path $repoRoot $RelativePath
    if ((Test-Path $fullPath) -and ((Get-Content $fullPath -Raw) -match $Pattern)) {
        Write-Host "[OK] $Name -> $RelativePath"
        return
    }

    Write-Host "[MISSING] $Name -> $RelativePath pattern '$Pattern'"
    $missing.Add($Name)
}

$paths = @(
    @{ Name = "Capa 1 / Buscador"; Path = "apps/web/src/app/page.tsx" },
    @{ Name = "Capa 1 / Formulario reporte evidencia"; Path = "apps/web/src/app/report/page.tsx" },
    @{ Name = "Capa 1 / Panel admin"; Path = "apps/web/src/app/admin/page.tsx" },
    @{ Name = "Capa 1 / Vista de grafo"; Path = "apps/web/src/app/graph/page.tsx" },
    @{ Name = "Capa 2 / FastAPI"; Path = "apps/api/app/main.py" },
    @{ Name = "Capa 2 / Pydantic schemas"; Path = "apps/api/app/schemas" },
    @{ Name = "Capa 2 / Auth endpoint"; Path = "apps/api/app/api/v1/endpoints/auth.py" },
    @{ Name = "Capa 2 / Security helpers"; Path = "apps/api/app/core/security.py" },
    @{ Name = "Capa 2 / Rate limit Redis"; Path = "apps/api/app/core/rate_limit.py" },
    @{ Name = "Capa 3 / Motor scoring"; Path = "apps/api/app/services/scoring.py" },
    @{ Name = "Capa 3 / Normalizador"; Path = "apps/api/app/services/normalizer.py" },
    @{ Name = "Capa 3 / Motor grafo"; Path = "apps/api/app/services/graph_engine.py" },
    @{ Name = "Capa 3 / Apelaciones"; Path = "apps/api/app/services/appeals.py" },
    @{ Name = "Capa 3 / Audit service"; Path = "apps/api/app/services/audit.py" },
    @{ Name = "Capa 4 / Celery app"; Path = "apps/worker/worker/celery_app.py" },
    @{ Name = "Capa 4 / Worker externo"; Path = "apps/worker/worker/tasks/external_checks.py" },
    @{ Name = "Capa 4 / Worker analisis"; Path = "apps/worker/worker/tasks/analysis.py" },
    @{ Name = "Capa 4 / Worker alertas"; Path = "apps/worker/worker/tasks/alerts.py" },
    @{ Name = "Capa 5 / Modelos PostgreSQL"; Path = "apps/api/app/models" },
    @{ Name = "Capa 5 / Modelo evidencia"; Path = "apps/api/app/models/evidence.py" },
    @{ Name = "Capa 6 / Fuentes externas config"; Path = "packages/shared/external_sources.json" },
    @{ Name = "Seguridad / Controles compartidos"; Path = "packages/shared/security_controls.json" },
    @{ Name = "Seguridad / EXIF API"; Path = "apps/api/app/services/exif.py" },
    @{ Name = "Seguridad / Politica Ley 29733"; Path = "docs/SECURITY_AND_PRIVACY.md" }
)

foreach ($item in $paths) {
    Test-ProjectPath -Name $item.Name -RelativePath $item.Path
}

$patterns = @(
    @{ Name = "Capa 1 / Cytoscape dependency"; Path = "apps/web/package.json"; Pattern = '"cytoscape"' },
    @{ Name = "Capa 5 / PostgreSQL service"; Path = "docker-compose.yml"; Pattern = '(?m)^\s*postgres:' },
    @{ Name = "Capa 5 / Redis service"; Path = "docker-compose.yml"; Pattern = '(?m)^\s*redis:' },
    @{ Name = "Capa 5 / Neo4j service"; Path = "docker-compose.yml"; Pattern = '(?m)^\s*neo4j:' },
    @{ Name = "Capa 5 / MinIO service"; Path = "docker-compose.yml"; Pattern = '(?m)^\s*minio:' },
    @{ Name = "Capa 2 / Keycloak optional service"; Path = "docker-compose.yml"; Pattern = '(?m)^\s*keycloak:' },
    @{ Name = "Capa 6 / VirusTotal"; Path = "packages/shared/external_sources.json"; Pattern = 'virustotal' },
    @{ Name = "Capa 6 / Safe Browsing"; Path = "packages/shared/external_sources.json"; Pattern = 'safe_browsing' },
    @{ Name = "Capa 6 / PhishTank"; Path = "packages/shared/external_sources.json"; Pattern = 'phishtank' },
    @{ Name = "Capa 6 / URLhaus"; Path = "packages/shared/external_sources.json"; Pattern = 'urlhaus' },
    @{ Name = "Capa 6 / urlscan"; Path = "packages/shared/external_sources.json"; Pattern = 'urlscan' }
)

foreach ($item in $patterns) {
    Test-ProjectPattern -Name $item.Name -RelativePath $item.Path -Pattern $item.Pattern
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Architecture check failed. Missing items: $($missing.Count)"
    exit 1
}

Write-Host ""
Write-Host "Architecture check passed. Repo structure matches the SVG blocks."
