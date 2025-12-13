@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
for /f "delims=" %%i in ("%ROOT%") do set "ROOT=%%~fi"

echo ==============================================
echo   AI RAG - Docker Desktop bootstrap (Windows)
echo ==============================================

where docker >nul 2>&1 || (
  echo [FATAL] Docker CLI not found. Install Docker Desktop and try again.
  exit /b 1
)

docker info >nul 2>&1 || (
  echo [FATAL] Docker Desktop is not running. Please start it and rerun this script.
  exit /b 1
)

set "ERRORFLAG=0"

call :compose_up "document-processor" "%ROOT%\document-processor" ".env"
call :compose_up "embedding_service" "%ROOT%\embedding_service" ""
call :compose_up "knowledge_base_api" "%ROOT%\knowledge_base_api" ".env.docker"
call :compose_up "rag_observability_stack" "%ROOT%\rag_observability_stack" ".env"

call :build_and_run "knowledge-search-api" "%ROOT%\knowledge-search-api" "knowledge-search-api" "8000:8000" ""
call :build_and_run "universal-embedder" "%ROOT%\universal_embedder" "universal-embedder" "8012:8012" ".env"
call :build_and_run "knowledge-base-bot" "%ROOT%\knowledge_base_bot" "knowledge-base-bot" "" ".env"

if "%ERRORFLAG%"=="1" (
  echo.
  echo One or more services failed to build or start. Review messages above.
  exit /b 1
) else (
  echo.
  echo All requested services have been processed. Containers that were not skipped should be running.
  exit /b 0
)

:compose_up
set "SERVICE=%~1"
set "DIR=%~2"
set "ENVFILE=%~3"

if not "%ENVFILE%"=="" if not exist "%DIR%\%ENVFILE%" (
  if exist "%DIR%\%ENVFILE%.example" (
    copy "%DIR%\%ENVFILE%.example" "%DIR%\%ENVFILE%" >nul
    echo [INFO] %SERVICE%: created %ENVFILE% from template; review credentials before rerun if needed.
  ) else (
    echo [SKIP] %SERVICE%: missing %ENVFILE% and no template found. Create it to start this service.
    goto :eof
  )
)

if not exist "%DIR%\docker-compose.yml" (
  echo [SKIP] %SERVICE%: docker-compose.yml not found.
  goto :eof
)

echo [UP] %SERVICE% via docker compose...
pushd "%DIR%" >nul
  docker compose up -d --build
  if errorlevel 1 (
    echo [ERROR] %SERVICE% failed to start via docker compose.
    set "ERRORFLAG=1"
  ) else (
    echo [OK] %SERVICE% is up.
  )
popd >nul
goto :eof

:build_and_run
set "SERVICE=%~1"
set "DIR=%~2"
set "IMAGE=%~3"
set "PORTS=%~4"
set "ENVFILE=%~5"

if not exist "%DIR%\Dockerfile" (
  echo [SKIP] %SERVICE%: Dockerfile not found.
  goto :eof
)

if not "%ENVFILE%"=="" if not exist "%DIR%\%ENVFILE%" (
  if exist "%DIR%\%ENVFILE%.example" (
    copy "%DIR%\%ENVFILE%.example" "%DIR%\%ENVFILE%" >nul
    echo [INFO] %SERVICE%: created %ENVFILE% from template; update secrets as needed.
  ) else (
    echo [WARN] %SERVICE%: %ENVFILE% not found; container will rely on built-in defaults.
  )
)

echo [BUILD] %SERVICE% image...
docker build -t %IMAGE% "%DIR%"
if errorlevel 1 (
  echo [ERROR] Failed to build %SERVICE% image.
  set "ERRORFLAG=1"
  goto :eof
)

echo [RUN] %SERVICE% container...
docker rm -f %IMAGE% >nul 2>&1
set "RUN_CMD=docker run -d --name %IMAGE%"
if not "%ENVFILE%"=="" if exist "%DIR%\%ENVFILE%" set "RUN_CMD=!RUN_CMD! --env-file \"%DIR%\%ENVFILE%\""
if not "%PORTS%"=="" set "RUN_CMD=!RUN_CMD! -p %PORTS%"
set "RUN_CMD=!RUN_CMD! %IMAGE%"
!RUN_CMD!
if errorlevel 1 (
  echo [ERROR] Failed to launch %SERVICE% container.
  set "ERRORFLAG=1"
) else (
  echo [OK] %SERVICE% container is running.
)
goto :eof
