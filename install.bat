@echo off
setlocal
title NyayaBandhu installation

powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0install.ps1"
if errorlevel 1 (
    echo.
    echo Installation failed. See the message above.
    pause
    exit /b 1
)

echo.
echo Installation complete. Use the NyayaBandhu desktop shortcut or start.bat.
pause
