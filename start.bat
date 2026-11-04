@echo off
setlocal
title NyayaBandhu
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo NyayaBandhu is not installed. Run install.bat first.
    pause
    exit /b 1
)

set "PYTHONPATH=%CD%\scripts"
if /i "%~1"=="fresh" goto fresh

set "NYAYA_CONSOLIDATION_DIR=%CD%\consolidation-data\visual-workspace"
echo Reusing workspace: %NYAYA_CONSOLIDATION_DIR%
goto launch

:fresh
if not exist "consolidation-data" mkdir "consolidation-data"
:new_store
set "NYAYA_CONSOLIDATION_DIR=%CD%\consolidation-data\recording-%RANDOM%-%RANDOM%"
if exist "%NYAYA_CONSOLIDATION_DIR%" goto new_store
mkdir "%NYAYA_CONSOLIDATION_DIR%"
if errorlevel 1 (
    echo Could not create a fresh workspace.
    pause
    exit /b 1
)
echo New empty workspace: %NYAYA_CONSOLIDATION_DIR%

:launch
echo Review workspace: http://127.0.0.1:8000/admin
echo Reader: http://127.0.0.1:8000/library
echo Close this window or press Ctrl+C to stop.
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000/admin'"
".venv\Scripts\python.exe" webui\run.py
if errorlevel 1 (
    echo NyayaBandhu stopped with an error.
    pause
    exit /b 1
)
