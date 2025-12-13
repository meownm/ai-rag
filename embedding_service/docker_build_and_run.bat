@echo off
setlocal

echo ----------------------------------------------------
echo  Docker Build and Run Script for Embeddings Service
echo ----------------------------------------------------
echo This script will build the Docker images and start all services
echo defined in docker-compose.yml (CPU, GPU, Postgres).
echo.

rem --- Step 1: Check Prerequisites ---
echo Checking for Docker...
docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop is not running or not installed.
    echo Please start Docker Desktop and ensure it is in 'Linux Containers' (WSL 2) mode.
    echo.
    pause
    exit /b 1
)
echo Docker is running.
echo.

rem Check for essential Docker files
if not exist "docker-compose.yml" (
    echo [ERROR] 'docker-compose.yml' not found in the current directory.
    pause
    exit /b 1
)
if not exist "Dockerfile.amd" (
    echo [ERROR] 'Dockerfile.amd' not found in the current directory.
    pause
    exit /b 1
)
echo All required Docker files found.
echo.

rem --- Step 2: Build and Run the Services ---
echo Building images and starting containers...
echo This may take a very long time on the first run as it downloads the ROCm base image.
echo.
echo ============================ DOCKER LOGS START ============================
echo.

rem The 'docker compose up' command will attach this console to the container logs.
rem The '--build' flag ensures images are rebuilt if the Dockerfile or source code changes.
docker compose up --build

rem The script will pause here until you stop the containers with Ctrl+C.
rem After you press Ctrl+C, the following cleanup commands will run.

echo.
echo ============================= DOCKER LOGS END =============================
echo.
echo Press any key to shut down and remove the containers...
pause
echo.

rem --- Step 3: Clean Up ---
echo Stopping and removing containers defined in docker-compose.yml...
rem 'docker compose down' stops and removes containers, networks, and volumes.
docker compose down

echo.
echo All services have been shut down.
pause
endlocal