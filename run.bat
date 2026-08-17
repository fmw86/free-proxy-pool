@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
if errorlevel 1 (
 echo.
 echo socks5-filter failed. Press any key to exit.
 pause >nul
 exit /b %errorlevel%
)
echo.
echo socks5-filter completed. Press any key to exit.
pause >nul
