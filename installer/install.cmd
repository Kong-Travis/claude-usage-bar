@echo off
rem Double-click launcher for install.ps1 (keep both files in the same folder).
rem Extra arguments are passed through, e.g.: install.cmd -Lang en
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
