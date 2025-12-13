@echo off
echo --- Updating Bot Dependencies and regenerating poetry.lock ---
echo This will find the latest allowed versions of packages and update the lock file.
echo This command should be run manually and with caution.
echo.

cd ..
poetry update

if %errorlevel% neq 0 (
    echo [!] An error occurred during dependency update.
    pause
    exit /b 1
)

echo.
echo [V] Dependencies have been updated.
echo The new 'poetry.lock' file should now be committed to your version control system.
pause