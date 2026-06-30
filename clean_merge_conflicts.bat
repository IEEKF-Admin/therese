@echo off
echo ========================================================
echo THERESE - Merge Conflict Marker Cleaner
echo ========================================================
echo.

cd /d C:\Django\therese

echo Bereinige Merge-Markierungen...

set "count=0"
for /r %%f in (*.py *.html *.js *.css *.txt *.md *.json) do (
    set /a count+=1
    echo [!count!] Bearbeite: %%~nxf
    powershell -NoProfile -Command ^
    "(Get-Content '%%f' -Raw) -replace '<<<<<<< HEAD', '' -replace '=======', '' -replace '>>>>>>> new-main', '' | Set-Content '%%f' -Encoding UTF8"
)

echo.
echo ========================================================
echo Fertig! %count% Dateien wurden verarbeitet.
echo Merge-Markierungen wurden entfernt.
echo ========================================================
echo.
pause