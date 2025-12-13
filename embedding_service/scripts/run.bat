@echo off
setlocal
title Embedding Service

:: ----------------------------------------------------
:: Скрипт для запуска FastAPI сервиса
:: ----------------------------------------------------

echo.
echo ===========================================
echo      Starting Embedding Service (FastAPI)
echo ===========================================
echo.

if not exist log_config.yaml (
    echo ERROR: Logging configuration file log_config.yaml not found.
    echo Please ensure the file exists in the project root.
    pause
    exit /b 1
)

echo Checking for virtual environment...
poetry run python -c "import torch" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Project dependencies are not installed.
    echo Please run install.bat first to set up the project.
    pause
    exit /b 1
)

echo Starting Uvicorn server with custom logging...
echo Service will run on your CPU. Models will be cached in memory.
echo API documentation will be available at http://localhost:8100/docs
echo To stop the service, press Ctrl+C in this window.
echo.

:: Запуск FastAPI сервиса через Uvicorn с указанием файла конфигурации логов
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8100 --reload --log-config log_config.yaml

echo.
echo The service has stopped.
pause
endlocal