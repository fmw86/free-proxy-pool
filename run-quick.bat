@echo off
setlocal
cd /d "%~dp0"

if not defined WORKERS set "WORKERS=50"
if not defined TIMEOUT set "TIMEOUT=8"
if not defined FAST_MS set "FAST_MS=5000"
if not defined LIMIT set "LIMIT=6000"

echo [quick] workers=%WORKERS% timeout=%TIMEOUT% fast_ms=%FAST_MS% limit=%LIMIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
if errorlevel 1 (
 echo.
 echo socks5-filter quick run failed. Press any key to exit.
 pause >nul
 exit /b %errorlevel%
)
echo.
echo socks5-filter quick run completed. Press any key to exit.
pause >nul
