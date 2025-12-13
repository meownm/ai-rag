@echo off
poetry add torch torchvision torchaudio --source pytorch_cu121
setlocal
title Search API - Installation
echo.
echo ===========================================
echo      Search API - Project Setup
echo ===========================================
echo.
echo [1/3] Checking dependencies (Python, Poetry)...
python --version >nul 2>&1 || (echo ERROR: Python not found! && goto :error)
poetry --version >nul 2>&1 || (echo ERROR: Poetry not found! && goto :error)
echo      ...OK
echo.
echo [2/3] Setting up .env file...
if not exist .env (copy .env.example .env >nul && echo      ...Created .env from template.) else (echo      ....env file already exists.)
echo      IMPORTANT: Please edit the .env file with your credentials.
echo.
echo [3/3] Installing dependencies with Poetry...
poetry install
if %errorlevel% neq 0 (echo ERROR: Poetry install failed. && goto :error)
echo.
echo ===========================================
echo      Installation completed successfully!
echo ===========================================
goto :end
:error
echo !!! Installation failed.
:end
pause