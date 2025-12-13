@echo off
setlocal

rem --- Configuration ---
set PYTHON_VERSION_MIN=10
set PYTHON_VERSION_MAX_EXCL=12

rem --- Derived Variables ---
set /a PYTHON_VERSION_MAX_EXCL_MINUS_ONE=%PYTHON_VERSION_MAX_EXCL% - 1

echo ----------------------------------------------------
echo  Environment Setup Script for Embeddings Service (Poetry)
echo ----------------------------------------------------
echo This script prepares the environment for running WITHOUT Docker.
echo.

rem --- Step 1: Check for helper script ---
if not exist "check_python_version.py" (
    echo [ERROR] Helper script 'check_python_version.py' not found.
    echo Please make sure it is in the same directory as this script.
    pause
    exit /b 1
)

rem --- Step 2: Check Python Version ---
echo Checking for Python 3.%PYTHON_VERSION_MIN% - 3.%PYTHON_VERSION_MAX_EXCL_MINUS_ONE%...

python check_python_version.py %PYTHON_VERSION_MIN% %PYTHON_VERSION_MAX_EXCL%
if %errorlevel% equ 1 (
    echo.
    echo [ERROR] No suitable Python version found (required: >=3.%PYTHON_VERSION_MIN% and ^<3.%PYTHON_VERSION_MAX_EXCL%).
    echo Please install a suitable Python version from the official website.
    pause
    exit /b 1
)
if %errorlevel% equ 2 (
    echo.
    echo [ERROR] Internal script error during Python version check.
    pause
    exit /b 1
)

echo Suitable Python version found.
echo.

rem --- Step 3: Check for Poetry ---
echo Checking for Poetry...
where poetry >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Poetry not found. Installing Poetry...
    curl -sSL https://install.python-poetry.org | python -
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Poetry.
        echo Please install it manually: https://python-poetry.org/docs/#installation
        pause
        exit /b 1
    )
    echo Poetry successfully installed.
    echo.
    echo Please RESTART this console or open a new one for Poetry to be available in PATH.
    echo Then run install_environment.bat again.
    pause
    exit /b 1
) else (
    echo Poetry found.
)
echo.

rem --- Step 4: Install Dependencies from pyproject.toml ---
echo Installing Python dependencies using Poetry...
rem Здесь мы должны явно добавить torch, так как он закомментирован в pyproject.toml для Docker
poetry add "torch>=2.1.0"
poetry install
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies using Poetry.
    pause
    exit /b 1
)
echo.

rem --- Step 5: Install DirectML for Windows GPU acceleration ---
echo Activating Poetry environment to install torch-directml...
for /f "tokens=*" %%i in ('poetry env info -p') do set "POETRY_VENV_PATH=%%i"
call "%POETRY_VENV_PATH%\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate Poetry virtual environment.
    pause
    exit /b 1
)

echo Installing torch-directml (GPU acceleration for Windows)...
pip install torch-directml
if %errorlevel% neq 0 (
    echo [WARNING] Failed to install torch-directml. The service will run on CPU only.
) else (
    echo torch-directml successfully installed.
)
deactivate
echo.

rem --- Finalization ---
echo Installation complete!
echo To run the service locally (without Docker), use 'run_server.bat'.
echo.
pause
endlocal