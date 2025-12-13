Write-Host "=== Document Processor Deployment ===" -ForegroundColor Cyan

# Проверка Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker не найден. Установите Docker Desktop и перезапустите PowerShell." -ForegroundColor Red
    exit 1
}

# Проверка docker compose v2
try {
    docker compose version | Out-Null
} catch {
    Write-Host "Docker Compose v2 не найден. Установите последнюю версию Docker Desktop." -ForegroundColor Red
    exit 1
}

# Сборка контейнера
Write-Host "=== Building image ===" -ForegroundColor Green
docker compose build

# Запуск контейнера
Write-Host "=== Starting service ===" -ForegroundColor Green
docker compose up -d

# Проверка состояния
Write-Host "`n=== Running containers ===" -ForegroundColor Cyan
docker ps

Write-Host "`n=== Logs (press Ctrl+C to stop) ===" -ForegroundColor Yellow
docker compose logs -f document-processor
