@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ==========================================
echo   THERESE - Git Version Push Script
echo ==========================================
echo.

:: Letzte Version aus Git-Tags holen
for /f "delims=" %%v in ('git describe --tags --abbrev=0 2^>nul') do (
    set "LAST_VERSION=%%v"
)
if not defined LAST_VERSION set "LAST_VERSION=v0.0.0"

echo Letzte verwendete Versionsnummer: %LAST_VERSION%
echo.

:: === Requirements.txt Handling ===
echo.
echo Pruefe auf virtuelle Umgebung fuer requirements.txt...
set "VENV_PYTHON="

for %%d in (venv .venv env) do (
    if exist "%%d\Scripts\python.exe" (
        set "VENV_PYTHON=%%d\Scripts\python.exe"
        goto :venv_found
    )
)

:venv_found
if defined VENV_PYTHON (
    echo Virtuelle Umgebung gefunden: %VENV_PYTHON%
    set /p "UPDATE_REQ=requirements.txt mit aktuellen Libraries aktualisieren? (j/n): "
    if /i "%UPDATE_REQ%"=="j" (
        echo.
        echo Aktualisiere requirements.txt ...
        "%VENV_PYTHON%" -m pip freeze > requirements.txt
        echo requirements.txt wurde aktualisiert.
        echo.
    )
) else (
    echo Keine virtuelle Umgebung gefunden.
    echo Bitte manuell sicherstellen, dass requirements.txt aktuell ist.
    echo.
)

set /p "NEW_VERSION=Neue Versionsnummer (z.B. 0.2.5): "
if "%NEW_VERSION:~0,1%"=="v" set "NEW_VERSION=%NEW_VERSION:~1%"

if "%NEW_VERSION%"=="" (
    echo.
    echo Keine Version eingegeben. Abbruch.
    pause
    exit /b 1
)

echo.
echo Aktueller Status:
git status --short
echo.

set /p "CONFIRM=Durchfuehren? (j/n): "
if /i not "%CONFIRM%"=="j" (
    echo.
    echo Abgebrochen.
    pause
    exit /b 0
)

echo.
echo === 1. Alle Änderungen stagen ===
git add .
if errorlevel 1 (
    echo Fehler beim git add.
    pause
    exit /b 1
)

echo.
set /p "COMMIT_MSG=Kurze, klare Beschreibung der Änderung: "
if "%COMMIT_MSG%"=="" (
    set "COMMIT_MSG=Release v%NEW_VERSION%"
) else (
    set "COMMIT_MSG=v%NEW_VERSION%: %COMMIT_MSG%"
)

echo.
echo === 2. Commit erstellen ===
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo Keine Änderungen zum Committen oder Fehler.
    echo.
    echo Setze Tag trotzdem fort...
) else (
    echo Commit erfolgreich.
)

echo.
echo === 3. Git Tag erstellen ===
git show-ref --verify --quiet "refs/tags/v%NEW_VERSION%" >nul 2>&1
if not errorlevel 1 (
    echo Tag v%NEW_VERSION% existiert bereits lokal.
    set /p "DELETE_TAG=Alten Tag lokal löschen und neu anlegen? (j/n): "
    set "DELETE_TAG=!DELETE_TAG: =!"
    if /i "!DELETE_TAG:~0,1!"=="j" (
        git tag -d v%NEW_VERSION%
        echo Tag gelöscht.
    ) else (
        echo Tag wird nicht neu erstellt.
        goto :skip_tag
    )
)
git tag -a v%NEW_VERSION% -m "Release v%NEW_VERSION%"
if errorlevel 1 (
    echo Tag existiert vielleicht bereits oder Fehler beim Taggen.
)
:skip_tag

echo.
echo === 4. Push zu Git ===
git push origin main --tags
if errorlevel 1 (
    echo.
    echo FEHLER beim Push!
    echo.
    echo Mögliche Ursachen und Lösungen:
    echo - Falsche oder veraltete Credentials für das Repo.
    echo   Manuell: git credential-manager erase
    echo   Dann erneut pushen (wird nach Token fragen).
    echo.
    echo - Keine Rechte auf das Repository (aktuell als KistianR auf IEEKF-Admin/therese).
    echo   Stelle sicher, dass du Push-Rechte hast oder verwende den richtigen Account/PAT.
    echo.
    echo - Branch heißt nicht "main" oder Remote ist nicht korrekt.
    echo   Manuell: git push origin main
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   ERFOLG! Version v%NEW_VERSION% wurde gepusht.
echo ==========================================
echo.
pause
exit /b 0
