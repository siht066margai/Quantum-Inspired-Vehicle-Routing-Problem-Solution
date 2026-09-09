@echo off
echo Starting SIH 2026 Traffic Route Optimizer Web Server...
start "" http://127.0.0.1:8000
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
) else (
    python -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
)