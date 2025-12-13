@echo off
setlocal

rem --- Configuration ---
set CPU_PORT=8001
set GPU_PORT=8002

echo ----------------------------------------------------
echo  Launch Script for Embeddings Service (Poetry)
echo ----------------------------------------------------
echo This script runs the service locally WITHOUT Docker.
echo.

rem --- Step 1: Check for Poetry ---
echo Checking for Poetry...
where poetry >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Poetry not found. Please run install_environment.bat first.
    pause
    exit /b 1
) else (
    echo Poetry found.
)
echo.

rem --- Step 2: Launch Services ---
rem Запускаем каждый uvicorn процесс в новом окне командной строки.
rem 'start cmd /k' - запускает новую консоль и оставляет ее открытой после выполнения команды.
rem 'poetry run' - выполняет команду внутри виртуального окружения Poetry.

echo Starting CPU service on port %CPU_PORT% (in a new window)...
start cmd /k "title Embeddings Service (CPU) & poetry run uvicorn main:app --host 0.0.0.0 --port %CPU_PORT% --workers 1 --log-level info & pause"

echo.
echo Starting GPU service on port %GPU_PORT% (in a new window)...
start cmd /k "title Embeddings Service (GPU/DirectML) & poetry run uvicorn main:app --host 0.0.0.0 --port %GPU_PORT% --workers 1 --log-level info & pause"

echo.
echo Services are launched.
echo CPU service is available at: http://localhost:%CPU_PORT%/v1/embeddings/cpu
echo GPU service is available at: http://localhost:%GPU_PORT%/v1/embeddings/gpu
echo.
echo Press any key in this window to terminate this script and attempt to stop the services.
pause

rem --- Step 3: Terminate Services ---
echo.
echo Terminating Uvicorn processes...
rem Используем заголовок окна для более точного завершения нужных процессов
taskkill /IM python.exe /F /FI "WINDOWTITLE eq Embeddings Service (CPU)" 2>nul
taskkill /IM python.exe /F /FI "WINDOWTITLE eq Embeddings Service (GPU/DirectML)" 2>nul
echo Services stopped.

endlocal