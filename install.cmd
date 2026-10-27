@echo off
rem Double-click to install or update AttendOps on Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
