# Windows installation

Use this installer for the visual review and amendment consolidation workspace.
It needs Windows 10 or later and an internet connection for Python or Python
packages that are not already installed.

## Install

1. Download and extract this branch's repository, or clone it on Windows.
2. Double-click `install.bat` at the repository root.
3. Choose a folder in the picker. Closing the picker uses
   `%LOCALAPPDATA%\NyayaBandhu`.

The installer copies the application, finds a 64-bit Python 3.9 or later, and
creates `.venv`. If Python is missing, it downloads the signed Python 3.12.4
installer from python.org and installs it for the current user in the chosen
folder. It installs `requirements.txt` and the local package, checks that the
review application imports, and creates a desktop shortcut.

The copy includes `data/` and `out/`, so the source PDFs and generated XML are
available for import. It excludes local review stores. Re-running the installer
updates application files without deleting the installed review stores.

For a command-line install with an explicit destination:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir 'C:\NyayaBandhu'
```

## Run

- Double-click the **NyayaBandhu** desktop shortcut or `start.bat` to reopen the
  persistent workspace in `consolidation-data\visual-workspace`.
- Double-click `start-fresh.bat` to create a separate empty recording workspace.
  Its path is printed in the console. Each run creates another workspace.
- The review workspace opens at `http://127.0.0.1:8000/admin`. The reader is at
  `http://127.0.0.1:8000/library`.

Close the console window or press Ctrl+C to stop the server. Stop any other
NyayaBandhu server on port 8000 before starting one.

## Import an Act for review

In the review workspace, choose **Add Act**, select a base XML document from
`out/base_act/eng/` and its matching source PDF from `data/`, then enter the
reviewer name and reason. The source files remain available for comparison.
No Act is imported into a new workspace automatically.

## Troubleshooting

| Problem | Action |
| --- | --- |
| `install.bat` says PowerShell is missing | Run the installer on Windows 10 or later with Windows PowerShell available. |
| Python download or package installation fails | Check the internet connection and rerun `install.bat`. |
| `start.bat` says NyayaBandhu is not installed | Run `install.bat` in this folder first. |
| Port 8000 is already in use | Close the other NyayaBandhu console window, then start again. |
| Browser does not open | Open `http://127.0.0.1:8000/admin` manually. |

The installer has been checked for script structure and application imports on
Linux. Windows execution still needs verification on a Windows machine.
