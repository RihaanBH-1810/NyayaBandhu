@echo off
setlocal enabledelayedexpansion

:: ====================================================================
:: NyayaBandhu — Start the viewer
::
:: Double-click this file to open the Akoma Ntoso document viewer in
:: your browser. The server runs until you close this window or press
:: Ctrl+C.
:: ====================================================================

title NyayaBandhu

:: Work from the directory this script lives in, so paths resolve
:: even when launched from a desktop shortcut.
cd /d "%~dp0"

echo.
echo  ===============================================
echo   NyayaBandhu — Akoma Ntoso Viewer
echo  ===============================================
echo.

:: ------------------------------------------------------------------
:: Find the Python interpreter
:: ------------------------------------------------------------------
:: Portable Python (downloaded by install.bat) is required.

set "PYTHON_EXE="

if exist "python\python.exe" (
    set "PYTHON_EXE=%~dp0python\python.exe"
)

if not defined PYTHON_EXE (
    echo  ERROR: Python was not found in this folder.
    echo.
    echo  Please run install.bat first to set up NyayaBandhu.
    echo.
    pause
    exit /b 1
)

:: ------------------------------------------------------------------
:: Open the browser, then start the server
:: ------------------------------------------------------------------
echo  Starting the viewer at http://127.0.0.1:8000
echo.
echo  Your browser will open automatically. If it does not,
echo  open the link above manually.
echo.
echo  To stop the server, close this window or press Ctrl+C.
echo  ===============================================
echo.

:: Launch the default browser after a short delay so the server
:: has time to start. The /b flag runs it in the background.
start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000"

:: Start the server (blocks until Ctrl+C or window close)
"!PYTHON_EXE!" webui/run.py
