@echo off
setlocal
title Project Installation

:: ... (секции 1-3 остаются без изменений) ...
echo.
echo ===========================================
echo            Project Setup
echo ===========================================
echo.
echo [1/4] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    goto :error
)
echo      ...Python found.
echo [2/4] Checking for Poetry...
poetry --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Poetry is not installed.
    goto :error
)
echo      ...Poetry found.
echo [3/4] Setting up .env configuration file...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
    )
)
echo.
echo      #####################################################################
echo      #  IMPORTANT: Open the .env file and fill in your actual           #
echo      #  credentials for PostgreSQL and MinIO.                           #
echo      #####################################################################
echo.

:: 4. Установка зависимостей
echo [4/5] Installing project dependencies with Poetry...
poetry install
if %errorlevel% neq 0 (
    echo ERROR: Poetry install failed. Please check the output above.
    goto :error
)

:: 5. === НОВАЯ СЕКЦИЯ: ПРОВЕРКА И ИНСТРУКЦИИ ДЛЯ NEO4J ===
echo.
echo [5/5] Checking for Knowledge Graph Database (Neo4j)...
echo.
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: Docker is not installed or not running.
    echo          Docker is the recommended way to run Neo4j for this project.
    echo          Please install Docker Desktop from https://www.docker.com/products/docker-desktop/
    echo.
) else (
    echo      ...Docker found.
)

echo.
echo      #################################################################################
echo      #  ACTION REQUIRED: Set up Neo4j Database                                       #
echo      # ----------------------------------------------------------------------------- #
echo      #  This project uses Neo4j for its Knowledge Graph feature.                     #
echo      #  The easiest way to run it is with Docker.                                    #
echo      #                                                                               #
echo      #  1. Open a new terminal (PowerShell or CMD).                                  #
echo      #  2. Run this command to start a Neo4j container:                              #
echo      #                                                                               #
echo      #     docker run --name doc-processor-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/your_neo4j_password neo4j:5-community
echo      #                                                                               #
echo      #  3. IMPORTANT: Replace 'your_neo4j_password' with a strong password.          #
echo      #  4. Update the NEO4J_PASSWORD in your .env file with the SAME password.       #
echo      #  5. You can access the Neo4j Browser at http://localhost:7474                 #
echo      #                                                                               #
echo      #  To disable this feature, set NEO4J_ENABLED=false in the .env file.           #
echo      #################################################################################
echo.


echo.
echo ===========================================
echo      Installation completed successfully!
echo ===========================================
echo.
goto :end

:error
echo.
echo !!! Installation failed. Please fix the errors and run again.
echo.

:end
pause
endlocal