@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM setup_therese.bat - Ersteinrichtung fuer THERESE auf Windows (frischer Clone)
REM Verwendung: setup_therese.bat [--prod] [--demo] [--with-media-import]

cd /d "%~dp0"

set "USE_PROD_SETTINGS=false"
set "WITH_DEMO=false"
set "WITH_MEDIA_IMPORT=false"

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--prod" set "USE_PROD_SETTINGS=true"
if /i "%~1"=="--demo" set "WITH_DEMO=true"
if /i "%~1"=="--with-media-import" set "WITH_MEDIA_IMPORT=true"
if /i "%~1"=="--help" goto show_help
shift
goto parse_args

:show_help
echo Verwendung: %~nx0 [--prod] [--demo] [--with-media-import]
exit /b 0

:args_done

echo ============================================================
echo   THERESE - Ersteinrichtung (Windows)
echo ============================================================
echo   Projekt: %CD%
echo.

set "SYS_PYTHON="
where py >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%p in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "SYS_PYTHON=%%p"
)
if not defined SYS_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "SYS_PYTHON=python"
)
if not defined SYS_PYTHON (
    echo FEHLER: Python 3 nicht gefunden.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('"%SYS_PYTHON%" --version 2^>^&1') do echo [OK] %%v

set "PYTHON=venv\Scripts\python.exe"
if exist "%PYTHON%" (
    echo [OK] Virtuelle Umgebung: venv\
) else (
    echo [..] Erstelle virtuelle Umgebung ...
    "%SYS_PYTHON%" -m venv venv
    if errorlevel 1 (
        echo FEHLER: venv konnte nicht erstellt werden.
        pause
        exit /b 1
    )
    echo [OK] Virtuelle Umgebung erstellt
)

echo [..] Aktualisiere pip ...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto pip_failed

echo [..] Installiere Abhaengigkeiten ...
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed
echo [OK] Python-Pakete installiert
goto pip_ok

:pip_failed
echo.
echo FEHLER: pip install fehlgeschlagen.
pause
exit /b 1

:pip_ok

if exist .env (
    echo [OK] .env vorhanden
) else (
    echo [..] Erstelle .env ...
    "%PYTHON%" create_env_template.py
    if errorlevel 1 (
        echo FEHLER: .env konnte nicht erstellt werden.
        pause
        exit /b 1
    )
    echo [OK] .env erstellt
)

if not exist logs mkdir logs
if not exist media mkdir media
if not exist staticfiles mkdir staticfiles
echo [OK] Verzeichnisse logs\, media\, staticfiles\

if "%USE_PROD_SETTINGS%"=="true" (
    set "DJANGO_SETTINGS_MODULE=therese.settings.base"
    echo [OK] Settings: therese.settings.base
) else (
    set "DJANGO_SETTINGS_MODULE=therese.settings"
    echo [OK] Settings: therese.settings
)
set "PYTHONUNBUFFERED=1"

echo.
echo [..] Django Systempruefung ...
"%PYTHON%" manage.py check
if errorlevel 1 goto django_failed

echo [..] Datenbank-Migrationen ...
"%PYTHON%" manage.py migrate --noinput
if errorlevel 1 goto django_failed

echo [..] Gruppen und Berechtigungen ...
"%PYTHON%" manage.py ensure_groups
if errorlevel 1 goto django_failed

echo [..] Statische Dateien (collectstatic) ...
"%PYTHON%" manage.py collectstatic --noinput
if errorlevel 1 goto django_failed

if "%WITH_MEDIA_IMPORT%"=="true" (
    echo [..] Importiere Legacy-Dateien aus media\ ...
    "%PYTHON%" manage.py import_media_to_database
) else (
    dir /s /b media\* >nul 2>&1
    if not errorlevel 1 (
        echo [..] Dateien in media\ gefunden - importiere ...
        "%PYTHON%" manage.py import_media_to_database
    ) else (
        echo [OK] Kein Legacy-Medienimport noetig
    )
)

if "%WITH_DEMO%"=="true" (
    echo [..] Erstelle Demo-Benutzer ...
    "%PYTHON%" create_demo_users.py
    echo [OK] Demo-Benutzer erstellt
)

if "%USE_PROD_SETTINGS%"=="true" (
    echo.
    echo [..] Deployment-Pruefung ...
    "%PYTHON%" manage.py check --deploy
)

echo.
echo [..] Admin-Benutzer anlegen (createsuperuser) ...
"%PYTHON%" manage.py createsuperuser
if errorlevel 1 echo   [HINWEIS] Superuser-Erstellung abgebrochen oder fehlgeschlagen.

echo.
echo ============================================================
echo   Ersteinrichtung abgeschlossen
echo ============================================================
echo.
echo Naechster Schritt - Server starten: start_therese.bat
echo.
echo Erneut ausfuehren ist sicher.
echo ============================================================
echo.
pause
exit /b 0

:django_failed
echo.
echo FEHLER: Django-Setup fehlgeschlagen.
pause
exit /b 1