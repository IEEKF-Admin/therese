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
echo DEBUG: Entering venv detection
echo Pruefe auf virtuelle Umgebung fuer requirements.txt...
set "VENV_PYTHON="

for %%d in (venv .venv env) do (
    echo DEBUG: Checking for %%d\Scripts\python.exe
    if exist "%%d\Scripts\python.exe" (
        echo DEBUG: Found venv in %%d
        set "VENV_PYTHON=%%d\Scripts\python.exe"
        goto :venv_found
    )
)

:venv_found
echo DEBUG: After loop, VENV_PYTHON=%VENV_PYTHON%
echo DEBUG: About to evaluate if defined VENV_PYTHON

if defined VENV_PYTHON goto :has_venv
goto :no_venv

:has_venv
echo DEBUG: ENTERED the if-defined block
echo Virtuelle Umgebung gefunden: %VENV_PYTHON%
set /p "UPDATE_REQ=requirements.txt mit aktuellen Libraries aktualisieren? Tippe j oder n: "
if /i "%UPDATE_REQ%"=="j" (
    echo.
    echo Aktualisiere requirements.txt ...
    "%VENV_PYTHON%" -m pip freeze > requirements.txt
    echo requirements.txt wurde aktualisiert.
    echo.
)
goto :after_venv_check

:no_venv
echo DEBUG: ENTERED the else block
echo Keine virtuelle Umgebung gefunden.
echo Bitte manuell sicherstellen, dass requirements.txt aktuell ist (pip freeze ^> requirements.txt).
echo.

:after_venv_check
echo DEBUG: Finished venv check block

set /p "NEW_VERSION=Neue Versionsnummer: "

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

set /p "CONFIRM=Durchfuehren? Tippe j oder n: "
if /i not "%CONFIRM%"=="j" (
    echo.
    echo Abgebrochen.
    pause
    exit /b 0
)

echo.
echo === 1. Alle Aenderungen stagen ===
git add .
if errorlevel 1 (
    echo Fehler beim git add.
    pause
    exit /b 1
)

echo.
echo === 2. Commit erstellen ===
git commit -m "Release %NEW_VERSION%"
if errorlevel 1 (
    echo Keine Aenderungen zum Committen oder Fehler.
    echo.
    echo Setze Tag trotzdem fort...
) else (
    echo Commit erfolgreich.
)

echo.
echo === 3. Git Tag erstellen ===
git tag -l %NEW_VERSION% >nul 2>&1
if not errorlevel 1 (
    echo Tag %NEW_VERSION% existiert bereits lokal.
    set /p "DELETE_TAG=Alten Tag lokal löschen und neu anlegen? (j/n): "
    if /i "%DELETE_TAG%"=="j" (
        git tag -d %NEW_VERSION%
    ) else (
        echo Tag wird nicht neu erstellt. Gehe zum Push über...
        goto :skip_tag
    )
)
git tag -a %NEW_VERSION% -m "Version %NEW_VERSION%"
if errorlevel 1 (
    echo Tag existiert vielleicht bereits oder Fehler beim Taggen.
)
:skip_tag

echo.
echo === 4. Push zu Git (Branch + Tags) ===
echo.
echo Aktueller Git-Remote:
git remote -v
echo.

echo.
set /p "FORCE_LOGIN=GitHub-Credentials zurücksetzen, um dich neu anzumelden (empfohlen bei 403-Fehler)? (j/n): "
if /i "%FORCE_LOGIN%"=="j" (
    echo.
    echo Lösche gespeicherte GitHub-Credentials...
    git credential-manager erase 2>nul || echo (Credential Manager nicht gefunden oder nichts zu löschen)
    echo.
    echo Credentials zurückgesetzt.
    echo Beim nächsten Push wirst du nach Username und Personal Access Token (PAT) gefragt.
    echo.
    echo WICHTIG: Verwende einen PAT mit 'repo'-Scope, nicht dein normales Passwort!
    echo Erzeuge einen unter: https://github.com/settings/tokens
)

echo.
echo Teste GitHub-Authentifizierung (kann einen Login-Prompt ausloesen)...
git ls-remote --heads origin
if errorlevel 1 (
    echo [Hinweis] Authentifizierungstest schlug fehl oder keine Berechtigung.
)

echo.
echo Starte Push (falls noch nicht authentifiziert, jetzt Prompt)...
git push origin HEAD --tags
if errorlevel 1 (
    echo.
    echo FEHLER beim Push!
    echo.
    echo Moegliche Ursachen:
    echo - Angemeldeter Benutzer (KistianR) hat keine Push-Rechte auf IEEKF-Admin/therese
    echo - Gespeicherte Credentials sind veraltet oder falsch (HTTPS + falscher Token)
    echo - Repository ist privat und der Token hat nicht den Scope 'repo'
    echo.
    echo Empfohlene Schritte zur Fehlerbehebung:
    echo 1. Credentials zuruecksetzen (zwingt zur Neuanmeldung):
    echo    git credential-manager erase
    echo    (Oder in neueren Git-Versionen: git credential-manager-core erase)
    echo    Danach beim naechsten Push nach Username + Personal Access Token (PAT) gefragt.
    echo.
    echo 2. Personal Access Token (PAT) erzeugen:
    echo    - Gehe zu https://github.com/settings/tokens
    echo    - 'Generate new token' (classic)
    echo    - Scope 'repo' aktivieren
    echo    - Token kopieren und beim Prompt als Passwort verwenden (nicht dein GitHub-Passwort!)
    echo.
    echo 3. Remote auf SSH umstellen (empfohlen fuer haeufige Nutzung):
    echo    git remote set-url origin git@github.com:IEEKF-Admin/therese.git
    echo    (Voraussetzung: SSH-Key auf GitHub hinterlegt)
    echo.
    echo 4. Manuell testen:
    echo    git push origin HEAD --tags
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   ERFOLG! Version %NEW_VERSION% wurde gepusht.
echo ==========================================
echo.
pause
exit /b 0
