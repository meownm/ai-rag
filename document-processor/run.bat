@echo off
setlocal
title Document Processor Service

:: ----------------------------------------------------
:: Скрипт для запуска FastAPI сервиса с фоновым воркером
:: ----------------------------------------------------

echo.
echo ===========================================
echo   Starting Document Processor Service (FastAPI)
echo ===========================================
echo.

if not exist .env (
    echo ERROR: Configuration file .env not found.
    echo Please run install.bat first to set up the project.
    pause
    exit /b 1
)

echo Starting Uvicorn server for main:app...
echo The background worker will start automatically.
echo Health check will be available at http://localhost:8010/health
echo To stop the service, press Ctrl+C in this window.
echo.

:: Запуск FastAPI сервиса через Uvicorn на порту 8010
poetry run uvicorn main:app --host 0.0.0.0 --port 8010 --reload

echo.
echo The service has stopped.
pause
endlocal