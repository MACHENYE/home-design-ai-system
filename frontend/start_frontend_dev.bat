@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

if not exist "node_modules" (
  echo [INFO] Installing frontend dependencies...
  call npm.cmd install
)

echo [INFO] Starting Vite dev server on http://127.0.0.1:5173 ...
echo [INFO] Press Ctrl+C to stop.
echo.

call npm.cmd run dev
