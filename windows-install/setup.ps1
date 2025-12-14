param(
    [switch]$SkipPull
)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Error "Файл .env не найден. Скопируйте .env.example и задайте значения переменных."
}

# Подгрузить переменные окружения из .env
Get-Content $envFile | Where-Object { $_ -and ($_ -notmatch '^#') } | ForEach-Object {
    $pair = $_ -split '=', 2
    if ($pair.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim())
    }
}

# Создать каталоги для volume, если их нет
$volumePaths = @(
    $env:POSTGRES_DATA_PATH,
    $env:KEYCLOAK_DATA_PATH,
    $env:MINIO_DATA_PATH
) | Where-Object { $_ -and ($_.Trim() -ne '') }

foreach ($path in $volumePaths) {
    if (-not (Test-Path $path)) {
        Write-Host "Создаю каталог $path" -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

# Скачивание образов
if (-not $SkipPull) {
    $images = @($env:POSTGRES_IMAGE, $env:KEYCLOAK_IMAGE, $env:MINIO_IMAGE)
    foreach ($image in $images) {
        if ($image -and ($image.Trim() -ne '')) {
            Write-Host "Загрузка образа $image" -ForegroundColor Cyan
            docker pull $image
        }
    }
}

# Запуск docker compose
Write-Host "Запуск docker compose" -ForegroundColor Green
docker compose --env-file $envFile -f (Join-Path $PSScriptRoot "docker-compose.yml") up -d

Pop-Location
