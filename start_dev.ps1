# start_dev.ps1
Write-Host "Starting Docker containers..." -ForegroundColor Cyan
docker compose -f docker/docker-compose.yml --env-file .env up -d

Write-Host "Waiting for Postgres to be healthy..." -ForegroundColor Cyan
$maxAttempts = 20
$attempt = 0
do {
    $attempt++
    Start-Sleep -Seconds 2
    $status = docker inspect --format='{{.State.Health.Status}}' docker-postgres-1 2>$null
    Write-Host "  Attempt $attempt/$maxAttempts - Postgres: $status"
} while ($status -ne "healthy" -and $attempt -lt $maxAttempts)

if ($status -ne "healthy") {
    Write-Host "Postgres failed to start!" -ForegroundColor Red
    exit 1
}

Write-Host "Running migrations..." -ForegroundColor Cyan
uv run alembic upgrade head

# Write-Host "Seeding data..." -ForegroundColor Cyan
# uv run python scripts/dev_setup.py

Write-Host "Starting app..." -ForegroundColor Green
uv run uvicorn src.main:app --reload