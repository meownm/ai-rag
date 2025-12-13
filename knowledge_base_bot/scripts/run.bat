@echo off
title KB Bot - Running
echo --- Starting Knowledge Base Bot ---
echo The bot is now running. Press CTRL+C to stop it.
echo.

REM Переходим в корневую папку бота
cd ..

REM Запускаем bot.py через виртуальное окружение Poetry
poetry run python bot.py
pause