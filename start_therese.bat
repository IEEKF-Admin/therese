@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================================
echo     THERESE - Development Server
echo ============================================================
echo.

set "PYTHON=venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo FEHLER: Virtuelle Umgebung nicht gefunden.
    echo Bitte zuerst anlegen: python -m venv venv
    pause
    exit /b 1
)

"%PYTHON%" --version
echo.

set "IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4" ^| findstr /V "127.0.0.1"') do (
    if not defined IP set "IP=%%a"
)
set "IP=%IP: =%"
if not defined IP set "IP=localhost"

echo   Lokal:    http://127.0.0.1:8000
echo   Netzwerk: http://%IP%:8000
echo.
echo   Beenden mit Ctrl+C
echo ============================================================
echo.

"%PYTHON%" manage.py runserver 0.0.0.0:8000

echo.
echo Server beendet.
pause