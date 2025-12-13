@echo off
title KB API - Installer
echo --- Knowledge Base API Service Installer ---

REM Проверяем, установлен ли Poetry
where poetry >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Poetry not found. Please install it first.
    pause
    exit /b 1
) else (
    echo [+] Poetry is installed.
)

echo.
echo [*] Installing API dependencies based on poetry.lock file...
cd ..

REM --no-root: не устанавливаем сам проект как библиотеку (КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ)
REM --with dev: устанавливаем также зависимости для разработки (pytest)
REM --sync: удаляет из окружения пакеты, которых больше нет в lock-файле
poetry install --no-root --with dev --sync

if %errorlevel% neq 0 (
    echo [!] An error occurred during dependency installation.
    pause
    exit /b 1
)

echo [V] Installation complete!
pause