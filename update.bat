@echo off
setlocal
title NyayaBandhu update
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install.bat before updating.
    pause
    exit /b 1
)
echo Close the NyayaBandhu server before updating.
".venv\Scripts\python.exe" scripts\update_windows.py %*
if errorlevel 1 (
    echo Update failed. See the message above.
    pause
    exit /b 1
)
pause
