@echo off
title KB API - Tests
echo --- Running Unit Tests for API ---
cd ..
poetry run pytest -v

if %errorlevel% neq 0 (
    echo [!] Tests failed.
    pause
) else (
    echo [V] All tests passed successfully.
)