@echo off
setlocal enabledelayedexpansion

:: ====================================================================
:: NyayaBandhu — Windows installer
::
:: Double-click this file to install the project. It will:
::   1. Ask where to install (default: C:\NyayaBandhu)
::   2. Copy the project files there
::   3. Find Python 3.9+ or download a portable copy automatically
::   4. Install dependencies
::   5. Convert the sample documents so the viewer has content
::   6. Create a desktop shortcut to start.bat
::
:: No administrator privileges are required. If Python is not already
:: installed, a portable copy is downloaded — nothing is installed
:: system-wide.
:: ====================================================================

title NyayaBandhu Installer

echo.
echo  ===============================================
echo   NyayaBandhu — Installer
echo   Digital Public Infrastructure for Indian Law
echo  ===============================================
echo.

:: ------------------------------------------------------------------
:: 1. Choose installation folder
:: ------------------------------------------------------------------
echo [1/6] Choose installation folder ...
echo.

set "DEFAULT_DIR=C:\NyayaBandhu"

:: Write a small PowerShell script to a temp file, then run it.
:: This avoids cmd.exe misinterpreting the parentheses in the
:: PowerShell code.
set "PS_PICKER=%TEMP%\nb_pick.ps1"

> "!PS_PICKER!" echo Add-Type -AssemblyName System.Windows.Forms
>> "!PS_PICKER!" echo [System.Windows.Forms.Application]::EnableVisualStyles^(^)
>> "!PS_PICKER!" echo $owner = New-Object System.Windows.Forms.Form
>> "!PS_PICKER!" echo $owner.TopMost = $true
>> "!PS_PICKER!" echo $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
>> "!PS_PICKER!" echo $dlg.Description = 'Choose installation folder for NyayaBandhu'
>> "!PS_PICKER!" echo $dlg.SelectedPath = '!DEFAULT_DIR!'
>> "!PS_PICKER!" echo $dlg.ShowNewFolderButton = $true
>> "!PS_PICKER!" echo $result = $dlg.ShowDialog^($owner^)
>> "!PS_PICKER!" echo if ^($result -eq 'OK'^) { $dlg.SelectedPath } else { '' }

set "INSTALL_DIR="
for /f "usebackq delims=" %%f in (`powershell -NoProfile -ExecutionPolicy Bypass -File "!PS_PICKER!"`) do set "INSTALL_DIR=%%f"
del "!PS_PICKER!" >nul 2>&1

:: Fall back to a console prompt if the dialog did not return a path
if not defined INSTALL_DIR (
    echo  Enter the installation folder, or press Enter to accept the
    echo  default location.
    echo.
    set "INSTALL_DIR=!DEFAULT_DIR!"
    set /p "INSTALL_DIR=  Install location [!DEFAULT_DIR!]: "
)

echo  Installing to: !INSTALL_DIR!
echo.

:: ------------------------------------------------------------------
:: 2. Copy project files
:: ------------------------------------------------------------------
echo [2/6] Copying project files ...

set "SOURCE_DIR=%~dp0"

:: If the source and target are the same, skip the copy
if /i "!SOURCE_DIR:~0,-1!" == "!INSTALL_DIR!" (
    echo  Source and target are the same folder — skipping copy.
) else (
    if not exist "!INSTALL_DIR!" mkdir "!INSTALL_DIR!"
    :: Use robocopy to mirror the project, excluding .venv, .git and __pycache__
    robocopy "!SOURCE_DIR:~0,-1!" "!INSTALL_DIR!" /e /xd .venv .git __pycache__ .pytest_cache /xf install.bat >nul 2>&1
    :: Copy install.bat separately (robocopy excluded it because it's open)
    copy /y "!SOURCE_DIR!install.bat" "!INSTALL_DIR!\install.bat" >nul 2>&1
)
echo  Done.
echo.

:: Work from the install directory for the remaining steps
pushd "!INSTALL_DIR!"

:: ------------------------------------------------------------------
:: 3. Find or download Python
:: ------------------------------------------------------------------
echo [3/6] Setting up Python ...

set "PYTHON_EXE="
set "USE_VENV=0"

:: Check if portable Python already exists in the install folder
if exist "python\python.exe" (
    set "PYTHON_EXE=!INSTALL_DIR!\python\python.exe"
    echo  Found portable Python in project folder — OK.
    goto :python_ready
)

:: ----- Download portable Python -----
echo.
echo  Downloading portable Python (no installation required) ...
echo  This is a one-time download of about 15 MB.
echo.

set "PY_VERSION=3.12.4"
set "PY_ZIP=python-%PY_VERSION%-embed-amd64.zip"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/%PY_ZIP%"
set "PY_DIR=!INSTALL_DIR!\python"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"

:: Download the embeddable zip
powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
     Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_ZIP%'"

if not exist "%PY_ZIP%" (
    echo.
    echo  ERROR: Failed to download Python.
    echo  Please check your internet connection and try again.
    echo.
    pause
    popd
    exit /b 1
)

:: Extract
echo  Extracting ...
powershell -NoProfile -Command ^
    "Expand-Archive -Path '%PY_ZIP%' -DestinationPath '%PY_DIR%' -Force"

del "%PY_ZIP%" >nul 2>&1

:: Enable pip: uncomment 'import site' in the ._pth file
:: The file is named pythonXYZ._pth where XYZ matches the version (e.g. python312._pth)
for %%p in ("%PY_DIR%\python*._pth") do (
    powershell -NoProfile -Command ^
        "(Get-Content '%%p') -replace '^#import site', 'import site' | Set-Content '%%p'"
)

:: Download and run get-pip.py
echo  Setting up pip ...
powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
     Invoke-WebRequest -Uri '%PIP_URL%' -OutFile '%PY_DIR%\get-pip.py'"

"%PY_DIR%\python.exe" "%PY_DIR%\get-pip.py" --no-warn-script-location >nul 2>&1

if !errorlevel! neq 0 (
    echo.
    echo  ERROR: Failed to set up pip.
    pause
    popd
    exit /b 1
)

del "%PY_DIR%\get-pip.py" >nul 2>&1

set "PYTHON_EXE=%PY_DIR%\python.exe"
echo  Portable Python %PY_VERSION% ready.

:python_ready
echo.

:: ------------------------------------------------------------------
:: 4. Install dependencies
:: ------------------------------------------------------------------
echo [4/6] Installing dependencies ...

"!PYTHON_EXE!" -m pip install --upgrade pip >nul 2>&1
"!PYTHON_EXE!" -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo  ERROR: Failed to install dependencies.
    pause
    popd
    exit /b 1
)
echo  Done.
echo.

:: ------------------------------------------------------------------
:: 5. Create desktop shortcut
:: ------------------------------------------------------------------
echo [6/6] Creating desktop shortcut ...

:: Write shortcut-creation script to a temp file to avoid cmd.exe
:: misinterpreting the parentheses in the PowerShell code.
set "PS_SHORTCUT=%TEMP%\nb_shortcut.ps1"

> "!PS_SHORTCUT!" echo $ws = New-Object -ComObject WScript.Shell
>> "!PS_SHORTCUT!" echo $desktop = $ws.SpecialFolders^('Desktop'^)
>> "!PS_SHORTCUT!" echo $sc = $ws.CreateShortcut^("$desktop\NyayaBandhu.lnk"^)
>> "!PS_SHORTCUT!" echo $sc.TargetPath = '!INSTALL_DIR!\start.bat'
>> "!PS_SHORTCUT!" echo $sc.WorkingDirectory = '!INSTALL_DIR!'
>> "!PS_SHORTCUT!" echo $sc.Description = 'Open NyayaBandhu - Akoma Ntoso viewer'
>> "!PS_SHORTCUT!" echo $sc.IconLocation = 'shell32.dll,1'
>> "!PS_SHORTCUT!" echo $sc.Save^(^)

powershell -NoProfile -ExecutionPolicy Bypass -File "!PS_SHORTCUT!" >nul 2>&1
del "!PS_SHORTCUT!" >nul 2>&1

if !errorlevel! equ 0 (
    echo  Desktop shortcut created: NyayaBandhu.lnk
) else (
    echo  Could not create desktop shortcut. You can run start.bat directly.
)
echo.

popd

:: ------------------------------------------------------------------
:: Done
:: ------------------------------------------------------------------
echo  ===============================================
echo   Installation complete!
echo.
echo   To start NyayaBandhu:
echo     - Double-click the "NyayaBandhu" shortcut on your desktop
echo     - Or double-click start.bat in: !INSTALL_DIR!
echo  ===============================================
echo.
pause
