# start.ps1
# Скрипт запуска. Загрузка .env и запуск сервиса.

$ErrorActionPreference = "Stop"
$dotEnvFile = ".env"

# --- 1. Чтение .env файла (Без проверок) ---
if (Test-Path $dotEnvFile) {
    Write-Host "Обнаружен файл '$dotEnvFile'. Загрузка переменных окружения..." -ForegroundColor Green
    Get-Content $dotEnvFile | ForEach-Object {
        if ($_ -match '^\s*#|^\s*$') { return }

        if ($_ -match '^(?<Key>[^=]+)=(?<Value>.*)$') {
            $key = $($matches.Key).Trim()
            $value = $($matches.Value).Trim().Trim('"').Trim("'")
            
            ${env:$key} = $value 
            Write-Host "-> Загружена переменная: $key"
        }
    }
} else {
    Write-Host "Файл '$dotEnvFile' не найден. Продолжение с глобальными ENV-переменными." -ForegroundColor Yellow
}

# --- 2. Запуск через Poetry ---
Write-Host "`n--- СТАРТ ---" -ForegroundColor Cyan
Write-Host "Запуск сервиса через poetry run start-worker (порт 8012 по умолчанию)..."
Write-Host "----------------"

poetry run start-worker