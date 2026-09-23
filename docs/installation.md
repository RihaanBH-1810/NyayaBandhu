# Installation (Windows)

Step-by-step guide for setting up and running NyayaBandhu on Windows. No
command-line knowledge is required, and nothing needs to be installed
manually — the installer handles everything.

## Prerequisites

| Requirement | Version | Notes |
| --- | --- | --- |
| Windows | 10 or later | — |
| Internet connection | — | Required for the first install only |

Python is **not** a prerequisite. If Python is already installed (3.9 or
later), the installer uses it. If it is not, the installer downloads a
portable copy automatically — nothing is installed system-wide.

## Installing

1. **Extract** the NyayaBandhu folder you received (if it came as a `.zip`).
2. **Double-click `install.bat`** inside the folder.

The installer will:

| Step | What it does |
| --- | --- |
| Choose folder | Opens a folder-picker dialog. Select a location, or close the dialog to accept the default (`C:\NyayaBandhu`). |
| Copy files | Copies the project to the chosen folder. Skipped if you are already running from that folder. |
| Set up Python | Uses your system Python if available (3.9+). Otherwise downloads a portable Python automatically (~15 MB, one-time). |
| Install dependencies | Downloads and installs the libraries the parser and viewer need. |
| Convert documents | Runs the parser over the sample legislative PDFs so the viewer has content to show immediately. |
| Desktop shortcut | Places a **NyayaBandhu** shortcut on your desktop. |

The whole process takes two to five minutes depending on your internet
connection.

## Starting the viewer

**Double-click the NyayaBandhu shortcut** on your desktop, or double-click
`start.bat` in the installation folder.

A console window will open and the viewer will start. Your browser opens
automatically at `http://127.0.0.1:8000`. You will see a list of converted
Acts; click one to read it.

On the first run (if installation was done without sample documents),
`start.bat` converts the sample PDFs before starting the viewer. This adds
about a minute.

## Stopping the viewer

Close the console window, or press **Ctrl+C** inside it. The viewer is a
local server that only your machine can reach; there is nothing to "log out"
of.

## Uninstalling

1. Delete the installation folder (the one you chose during install).
2. Delete the **NyayaBandhu** shortcut from your desktop.

No registry entries, system files, or system-wide packages are modified during
installation.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| **Folder picker does not appear** | The installer uses a Windows dialog via PowerShell. If it does not appear, the default location (`C:\NyayaBandhu`) is used automatically. |
| **"Failed to download Python"** | Check your internet connection. The installer downloads Python from python.org. If you are behind a corporate proxy, ask your IT team for help. |
| **"Failed to install dependencies"** | Check your internet connection. The installer downloads libraries from PyPI. If you are behind a corporate proxy, ask your IT team for the proxy address and set the `HTTPS_PROXY` environment variable. |
| **Firewall warning when starting the viewer** | Windows Defender may ask whether to allow Python to accept connections. Click **Allow**. The viewer only listens on `127.0.0.1` (your own machine). |
| **"Address already in use" when starting** | Another program is using port 8000. Close it, or stop a previous NyayaBandhu instance first. |
| **Browser does not open automatically** | Open your browser and go to `http://127.0.0.1:8000` manually. |
| **Desktop shortcut does not work** | The installation folder may have been moved or deleted. Run `install.bat` again. |

## How the scripts work

### `install.bat`

| Component | Detail |
| --- | --- |
| Folder picker | PowerShell `FolderBrowserDialog` |
| File copy | `robocopy`, excluding `.venv`, `.git`, `__pycache__` |
| System Python check | `where python` + version comparison |
| Portable Python | [Embeddable package](https://www.python.org/downloads/) (3.12.4, ~15 MB), extracted to `python\` |
| pip bootstrap | `get-pip.py` from [bootstrap.pypa.io](https://bootstrap.pypa.io/get-pip.py), with `import site` enabled in the `._pth` file |
| Dependencies | `pip install -r requirements.txt` |
| Document conversion | `scripts/akn-parser.py -t base_act -l eng` |
| Desktop shortcut | PowerShell `WScript.Shell` COM object |

### `start.bat`

| Component | Detail |
| --- | --- |
| Python detection | Checks `python\python.exe` (portable) first, then `.venv\Scripts\python.exe` (system venv) |
| First-run conversion | Converts sample documents if `out\` has no XML files |
| Browser launch | `start http://127.0.0.1:8000` after a 2-second delay |
| Server | `.venv\Scripts\python webui/run.py` or `python\python.exe webui/run.py` |
