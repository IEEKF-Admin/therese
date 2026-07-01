@echo off
chcp 65001 >nul 2>&1

echo ============================================================
echo   THERESE - Pip Repair (fixes broken rich/box error)
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/4] Downloading fresh get-pip.py ...
powershell -NoProfile -Command "Invoke-WebRequest -Uri https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py -UseBasicParsing"

if not exist get-pip.py (
    echo ERROR: Could not download get-pip.py
    pause
    exit /b 1
)

echo [2/4] Reinstalling pip using venv Python...
venv\Scripts\python.exe get-pip.py --force-reinstall

if errorlevel 1 (
    echo.
    echo Repair failed. Try running the PowerShell commands manually.
    pause
    exit /b 1
)

echo [3/4] Upgrading pip...
venv\Scripts\python.exe -m pip install --upgrade pip

echo [4/4] Installing whitenoise...
venv\Scripts\python.exe -m pip install whitenoise

echo.
echo Cleaning up...
del get-pip.py >nul 2>&1

echo.
echo ============================================================
echo   Pip repair completed!
echo   Now try: .\start_therese.bat
echo ============================================================
echo.
pause
