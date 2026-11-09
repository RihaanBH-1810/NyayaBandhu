param(
    [string]$InstallDir
)

$ErrorActionPreference = 'Stop'
$sourceDir = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$defaultDir = Join-Path $env:LOCALAPPDATA 'NyayaBandhu'

function Select-InstallDir {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = 'Choose a folder for NyayaBandhu'
        $dialog.SelectedPath = $defaultDir
        $dialog.ShowNewFolderButton = $true
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
            return $dialog.SelectedPath
        }
    } catch {
        Write-Host 'Folder picker unavailable. Using the default location.'
    }
    return $defaultDir
}

function Find-Python {
    param([string]$LocalPython)

    $perUserPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    $perUserPython64 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312-64\python.exe'
    $registeredPython = $null
    $installKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Python\PythonCore\3.12\InstallPath')
    if ($installKey) {
        $registeredPython = $installKey.GetValue('ExecutablePath')
        $registeredRoot = $installKey.GetValue('')
        if (-not $registeredPython -and $registeredRoot) {
            $registeredPython = Join-Path $registeredRoot 'python.exe'
        }
        $installKey.Close()
    }
    $candidates = @(
        @{ File = $LocalPython; Args = @() },
        @{ File = $registeredPython; Args = @() },
        @{ File = $perUserPython; Args = @() },
        @{ File = $perUserPython64; Args = @() },
        @{ File = 'py.exe'; Args = @('-3.12') },
        @{ File = 'py.exe'; Args = @('-3') },
        @{ File = 'python.exe'; Args = @() }
    )
    foreach ($candidate in $candidates) {
        try {
            $candidateArgs = $candidate.Args
            & $candidate.File @candidateArgs -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) and sys.maxsize > 2**32 else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }
    return $null
}

try {
    if (-not $InstallDir) { $InstallDir = Select-InstallDir }
    $InstallDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
    if (-not $InstallDir) { throw 'Choose an installation folder.' }

    Write-Host "Installing NyayaBandhu in $InstallDir"
    if (-not [string]::Equals($sourceDir, $InstallDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        if ($InstallDir.StartsWith($sourceDir + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Choose a folder outside the source checkout, or install in the checkout itself.'
        }
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        Write-Host 'Copying application files...'
        & robocopy.exe $sourceDir $InstallDir /E /XD .git .venv consolidation-data review-data __pycache__ .pytest_cache python /XF *.pyc *.pyo | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "File copy failed (robocopy code $LASTEXITCODE)." }
    }

    Set-Location $InstallDir
    $localPython = Join-Path $InstallDir 'python\python.exe'
    $python = Find-Python $localPython
    if (-not $python) {
        $version = '3.12.4'
        $download = Join-Path $env:TEMP "nyayabandhu-python-$version-amd64.exe"
        $url = "https://www.python.org/ftp/python/$version/python-$version-amd64.exe"
        Write-Host "Downloading Python $version from python.org..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $download
        $signature = Get-AuthenticodeSignature $download
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
            throw 'The downloaded Python installer did not have a valid Python Software Foundation signature.'
        }
        $process = Start-Process -FilePath $download -ArgumentList '/quiet InstallAllUsers=0 Include_pip=1 Include_launcher=0 PrependPath=0 Include_test=0' -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Python installer exited with code $($process.ExitCode)."
        }
        Remove-Item $download -ErrorAction SilentlyContinue
        $python = Find-Python $localPython
        if (-not $python) {
            throw "Python installer finished, but 64-bit Python 3.9 or later was not found. Check $env:LOCALAPPDATA\Programs\Python and rerun the installer."
        }
    }

    $venvPython = Join-Path $InstallDir '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        Write-Host 'Creating the Python environment...'
        $pythonArgs = $python.Args
        & $python.File @pythonArgs -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }

    Write-Host 'Installing dependencies...'
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & $venvPython -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw 'Application installation failed.' }
    & $venvPython -c 'import fastapi, uvicorn, akn_consolidator, webui.workspace'
    if ($LASTEXITCODE -ne 0) { throw 'The installed application could not be imported.' }
    Write-Host 'Application imports verified.'

    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path $shell.SpecialFolders('Desktop') 'NyayaBandhu.lnk'))
        $shortcut.TargetPath = Join-Path $InstallDir 'start.bat'
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = 'Open the NyayaBandhu review workspace'
        $shortcut.Save()
        Write-Host 'Desktop shortcut created.'
    } catch {
        Write-Warning 'Could not create the desktop shortcut. Use start.bat in the installation folder.'
    }

    Write-Host 'Installation complete.'
    Write-Host "Persistent workspace: $InstallDir\start.bat"
    Write-Host "Fresh recording workspace: $InstallDir\start-fresh.bat"
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
