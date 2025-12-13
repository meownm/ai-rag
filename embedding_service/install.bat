@echo off
setlocal
title Embedding Service Installation

:: ----------------------------------------------------
:: Скрипт для установки окружения и зависимостей
:: ----------------------------------------------------

echo.
echo ===========================================
echo            Project Setup
echo ===========================================
echo.

echo [1/3] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ and make sure it's added to your PATH.
    goto :error
)
echo      ...Python found.

echo.
echo [2/3] Checking for Poetry...
poetry --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Poetry is not installed.
    echo Please follow the installation instructions at https://python-poetry.org/docs/
    goto :error
)
echo      ...Poetry found.

echo.
echo [3/3] Installing project dependencies with Poetry...
echo This might take a few minutes, especially when downloading PyTorch.
poetry install
if %errorlevel% neq 0 (
    echo ERROR: Poetry install failed. Please check the output above.
    goto :error
)

echo.
echo.
echo      #####################################################################
echo      #  IMPORTANT INFORMATION FOR WINDOWS SETUP                          #
echo      # ----------------------------------------------------------------- #
echo      #  - This service will run on your CPU.                             #
echo      #    (Native AMD GPU acceleration is only supported via Docker/Linux) #
echo      #                                                                   #
echo      #  - The first time you request a specific model via the API,       #
echo      #    it will be downloaded from Hugging Face. This might take       #
echo      #    some time and requires an internet connection.                 #
echo      #                                                                   #
echo      #  - To start the service, simply run the 'run.bat' file.           #
echo      #####################################################################
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