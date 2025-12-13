@echo off
echo --- Knowledge Base Bot Installer ---

REM Проверяем, установлен ли Poetry
where poetry >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Poetry not found. Please install it first.
    echo Follow the instructions here: https://python-poetry.org/docs/#installation
    pause
    exit /b 1
) else (
    echo [+] Poetry is installed.
)

echo.
echo [*] Installing bot dependencies using Poetry...
echo This may take a few minutes.

REM Переходим в корневую папку бота
cd ..

REM Устанавливаем ТОЛЬКО зависимости, не пытаясь установить сам проект
poetry install --no-root

if %errorlevel% neq 0 (
    echo [!] An error occurred during dependency installation.
    pause
    exit /b 1
)

echo.
echo [V] Installation complete!
echo You can now run the bot using the 'run.bat' script.
pause