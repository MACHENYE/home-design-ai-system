@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "CONDA_ROOT=D:\_APPS\Miniconda"
set "CONDA_ENV=home-design-ai"
set "CONDA_ENV_DIR=%CONDA_ROOT%\envs\%CONDA_ENV%"
set "CONDA_ACTIVATE=%CONDA_ROOT%\Scripts\activate.bat"

if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo Checking project startup requirements...
echo.

if not exist "%CONDA_ACTIVATE%" (
  echo [ERROR] Miniconda activate script not found:
  echo %CONDA_ACTIVATE%
  echo.
  pause
  exit /b 1
)

if not exist "%CONDA_ENV_DIR%" (
  echo [ERROR] Conda environment not found:
  echo %CONDA_ENV_DIR%
  echo.
  pause
  exit /b 1
)

if not exist "%PROJECT_DIR%\run.py" (
  echo [ERROR] Backend startup file not found:
  echo %PROJECT_DIR%\run.py
  echo.
  pause
  exit /b 1
)

if not exist "%PROJECT_DIR%\frontend\package.json" (
  echo [ERROR] Frontend package file not found:
  echo %PROJECT_DIR%\frontend\package.json
  echo.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found in PATH.
  echo Please install Node.js or add npm to PATH, then run this script again.
  echo.
  pause
  exit /b 1
)

echo Starting backend and frontend in separate windows...
echo Backend:  http://127.0.0.1:8001
echo Frontend: http://127.0.0.1:5173
echo.

start "Home Design Backend" cmd /k "cd /d ^"%PROJECT_DIR%^" && call ^"%CONDA_ACTIVATE%^" ^"%CONDA_ENV_DIR%^" && python run.py"
start "Home Design Frontend" cmd /k "cd /d ^"%PROJECT_DIR%\frontend^" && call ^"%CONDA_ACTIVATE%^" ^"%CONDA_ENV_DIR%^" && npm run dev"

echo Startup commands have been sent.
echo Close the Backend or Frontend window to stop that service.
echo.
pause
