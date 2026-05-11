@echo off
setlocal enabledelayedexpansion

REM Ensure UTF-8 output (helps with Chinese paths)
chcp 65001 >nul

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Missing venv python: "%cd%\.venv\Scripts\python.exe"
  echo Create it first with: uv venv --python 3.11 .venv
  exit /b 1
)

REM If port 8001 is already in use, stop the listener(s) first.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8001 ^| findstr LISTENING') do (
  echo [INFO] Port 8001 is in use. Stopping PID %%p ...
  taskkill /PID %%p /F >nul 2>&1
)

REM Give Windows a moment to release the socket.
>nul timeout /t 1 /nobreak

echo [INFO] Starting backend on http://127.0.0.1:8001 ...
echo [INFO] Press Ctrl+C to stop.
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8001
