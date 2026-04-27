@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0backend"
call start_backend.bat
