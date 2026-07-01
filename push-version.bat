@echo off
chcp 65001 >nul

:: ============================================
:: Force execution in cmd.exe (fixes "." error from PowerShell)
:: ============================================
if not "%~1"==":cmd" (
    cmd.exe /c "%~f0" :cmd %*
    exit /b
)

cd /d "%~dp0"

echo ==========================================
echo   THERESE - Einfacher Git Push
echo ==========================================
echo.

git status --short
echo.

set /p "COMMIT_MSG=Kurze, klare Beschreibung der Änderung: "

if "%COMMIT_MSG%"=="" (
    echo.
    echo Keine Beschreibung eingegeben. Abbruch.
    pause
    exit /b 1
)

echo.
echo === git add . ===
git add .

if errorlevel 1 (
    echo Fehler beim git add.
    pause
    exit /b 1
)

echo.
echo === git commit ===
git commit -m "%COMMIT_MSG%"

if errorlevel 1 (
    echo.
    echo Commit fehlgeschlagen (keine Änderungen oder Fehler).
    pause
    exit /b 1
)

echo.
echo === git push origin main ===
git push origin main

if errorlevel 1 (
    echo.
    echo Push fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   Fertig! Änderungen wurden gepusht.
echo ==========================================
echo.
pause
exit /b 0
