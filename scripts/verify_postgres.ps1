<#
.SYNOPSIS
  Verify or launch local PostgreSQL for OncoTwin-BRCA.
#>

$ErrorActionPreference = "Continue"

Write-Host "Checking Docker status..." -ForegroundColor Cyan
$dockerStatus = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] Docker engine is currently not running or desktop service is stopped." -ForegroundColor Yellow
    Write-Host "To start PostgreSQL:" -ForegroundColor Yellow
    Write-Host "  1. Start Docker Desktop from your Windows Start Menu."
    Write-Host "  2. Run: docker compose --env-file .env -f infra/docker-compose.yml up -d"
    Write-Host "  3. Run: .\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head"
    Write-Host "  4. Run: .\.venv\Scripts\python.exe -m pytest backend/tests/test_database.py -k test_postgresql"
    exit 0
}

Write-Host "Docker is running! Starting PostgreSQL container..." -ForegroundColor Green
docker compose --env-file .env -f infra/docker-compose.yml up -d

Write-Host "Waiting for database readiness..." -ForegroundColor Cyan
Start-Sleep -Seconds 4

Write-Host "Applying Alembic database migrations..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head

Write-Host "Running PostgreSQL integration tests..." -ForegroundColor Green
$env:POSTGRES_TEST_URL = "postgresql+psycopg://oncotwin:oncotwin_local_dev_secret_2026!@127.0.0.1:5432/oncotwin"
.\.venv\Scripts\python.exe -m pytest backend/tests/test_database.py -k test_postgresql_integration_and_concurrency -v
