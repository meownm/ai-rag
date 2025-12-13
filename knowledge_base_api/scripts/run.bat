@echo off
title KB API - Running
echo --- Starting Knowledge Base API Service (Local) ---
cd ..
poetry run uvicorn main:app --host 0.0.0.0 --port 8001 --reload