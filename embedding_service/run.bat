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

echo Checking for virtual environment...
poetry run python -c "import torch" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Project dependencies are not installed.
    echo Please run install.bat first to set up the project.
    pause
    exit /b 1
)

echo Starting Uvicorn server...
echo Service will run on your CPU. Models will be cached in memory.
echo API documentation will be available at http://localhost:8100/docs
echo To stop the service, press Ctrl+C in this window.
echo.

:: Запуск FastAPI сервиса через Uvicorn на порту 8100
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8100 --reload

echo.
echo The service has stopped.
pause
endlocal