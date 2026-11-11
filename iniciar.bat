@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
start "" http://localhost:8000
uv run python -m clipes
pause
