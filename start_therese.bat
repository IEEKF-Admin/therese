@echo off

echo DEBUG: === Script started ===
echo DEBUG: Arg1 = [%~1]
echo DEBUG: COMSPEC = [%COMSPEC%]
echo.

REM Force cmd.exe
@if not "%~1"==":cmd" (
    cmd /c "%~f0" :cmd %*
    exit /b
)

echo DEBUG: === Running in cmd.exe ===
echo.

cls
echo ============================================================
echo     THERESE - DEMO START (Netzwerk-Zugriff)
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/3] Aktiviere virtuelle Umgebung...
call venv\Scripts\activate.bat >nul 2>&1

echo [2/3] Ermittle IP-Adresse...
echo.

setlocal enabledelayedexpansion
set "IP="

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
    set "candidate=%%a"
    set "candidate=!candidate: =!"
    if not "!candidate!"=="127.0.0.1" (
        if "!IP!"=="" set "IP=!candidate!"
    )
)

if "!IP!"=="" set "IP=IP-NICHT-GEFUNDEN"

endlocal & set "IP=%IP%"

echo DEBUG: Detected IP = [%IP%]

echo ============================================================
echo.
echo   SERVER LAEUFT JETZT FUER NETZWERK-ZUGRIFF!
echo.
echo   Zugriffs-URL: http://%IP%:8000
echo.
echo ============================================================
echo.

echo DEBUG: === Writing current_demo_url.txt (using PowerShell to avoid > issues) ===

powershell -NoProfile -Command "Set-Content -Path 'current_demo_url.txt' -Value 'http://%IP%:8000' -Encoding ASCII"

echo DEBUG: File write via PowerShell completed.
echo Die aktuelle URL wurde in "current_demo_url.txt" gespeichert.

python manage.py runserver 0.0.0.0:8000

echo.
echo Server wurde beendet.
pause