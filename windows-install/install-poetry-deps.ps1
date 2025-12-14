[CmdletBinding()]
param(
    [switch]$ForceLock
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$Projects = @(
    "document-processor",
    "embedding_backfill_worker",
    "embedding_service",
    "knowledge-search-api",
    "knowledge_base_api",
    "knowledge_base_api/knowledge_base_api1",
    "knowledge_base_bot",
    "universal_embedder"
)

function Ensure-Poetry {
    if (Get-Command poetry -ErrorAction SilentlyContinue) {
        return
    }

    Write-Host "Poetry не найден. Устанавливаем через официальный установщик..."
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python должен быть установлен и доступен в PATH."
    }

    (Invoke-WebRequest -Uri "https://install.python-poetry.org" -UseBasicParsing).Content | & $python.Source -

    $userScripts = Join-Path $HOME "AppData\\Roaming\\Python\\Scripts"
    if (Test-Path $userScripts -and (-not ($env:Path.Split(';') -contains $userScripts))) {
        $env:Path = "$userScripts;$env:Path"
        Write-Host "Добавлен путь к Poetry: $userScripts"
    }
}

function Update-LockFile {
    param(
        [switch]$Force
    )

    if (-not (Test-Path "poetry.lock") -or $Force) {
        Write-Host "Генерация poetry.lock..."
        poetry lock
        return
    }

    Write-Host "Проверка актуальности poetry.lock..."
    poetry lock --check
    if ($LASTEXITCODE -ne 0) {
        Write-Host "poetry.lock устарел. Пересоздаем..."
        poetry lock
    }
}

function Install-ProjectDependencies {
    param(
        [string]$ProjectPath
    )

    $fullPath = Join-Path $RepoRoot $ProjectPath
    if (-not (Test-Path $fullPath)) {
        Write-Warning "Каталог $ProjectPath не найден, пропускаем."
        return
    }

    if (-not (Test-Path (Join-Path $fullPath "pyproject.toml"))) {
        Write-Warning "В $ProjectPath нет pyproject.toml, пропускаем."
        return
    }

    Push-Location $fullPath
    try {
        Update-LockFile -Force:$ForceLock
        Write-Host "Установка зависимостей в $ProjectPath..."
        poetry install
    }
    finally {
        Pop-Location
    }
}

Ensure-Poetry

foreach ($project in $Projects) {
    Install-ProjectDependencies -ProjectPath $project
}

Write-Host "Готово."
