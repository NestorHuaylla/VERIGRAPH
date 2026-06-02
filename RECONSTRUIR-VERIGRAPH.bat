@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-dev.ps1" -ForceBuild
if errorlevel 1 pause
