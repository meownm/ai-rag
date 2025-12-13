@echo off
setlocal
title Search API - Service
echo.
echo ===========================================
echo   Starting Knowledge Search API (FastAPI)
echo ===========================================
echo.
if not exist .env (echo ERROR: .env not found. Please run install.bat first. && pause && exit /b 1)
echo Starting Uvicorn server...
echo API will be available at http://localhost:8020
echo To stop the service, press Ctrl+C.
echo.
poetry run uvicorn main:app --host 0.0.0.0 --port 8020 --reload
pause