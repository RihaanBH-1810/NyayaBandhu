# Windows installation

Use this installer for the visual review and amendment consolidation workspace.
It needs Windows 10 or later and an internet connection for Python or Python
packages that are not already installed.

## Install

1. Download and **extract the entire ZIP** to a normal folder, or clone the
   repository on Windows. Do not double-click `install.bat` inside the ZIP
   preview, which runs it from a temporary folder.
2. Double-click `install.bat` at the repository root.
3. Choose a folder in the picker. Closing the picker uses
   `%LOCALAPPDATA%\NyayaBandhu`.

The installer copies the application, finds a 64-bit Python 3.9 or later, and
creates `.venv`. If Python is missing, it downloads the signed Python 3.12.4
installer from python.org and installs it in the current user's standard Python
directory under `%LOCALAPPDATA%\Programs\Python`. It installs `requirements.txt`
and the local package, checks that the
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
- `start.bat` reopens the same review workspace, so imported Acts, drafts,
  approvals and amendments remain available after restarting. Re-running
  `install.bat` updates the app while preserving the installed review store.
- The review workspace opens at `http://127.0.0.1:8000/admin`. The reader is at
  `http://127.0.0.1:8000/library`.

Close the console window or press Ctrl+C to stop the server. Stop any other
NyayaBandhu server on port 8000 before starting one.

## Import an Act for review

In the review workspace, choose **Add Act**, select a base XML document from
`out/base_act/eng/` and its matching source PDF from `data/`, then enter the
reviewer name and reason. The source files remain available for comparison.
No Act is imported into a new workspace automatically.

The Upload amendment menu lists prepared amendments for the Act currently open.
The Acts page and each Act timeline have Delete controls. Deleted Acts and
amendments can be restored from their respective Deleted sections. An amendment
used by a saved version cannot be deleted until that version's dependency is
resolved. The reviewer name and reason are recorded for each delete or restore.

## Troubleshooting

| Problem | Action |
| --- | --- |
| `install.bat` says PowerShell is missing | Run the installer on Windows 10 or later with Windows PowerShell available. |
| Installer says to extract the ZIP | In File Explorer, right-click the ZIP, choose **Extract All**, open the extracted `NyayaBandhu` folder, then run `install.bat`. |
| Python download or package installation fails | Check the internet connection and rerun `install.bat`. |
| `start.bat` says NyayaBandhu is not installed | Run `install.bat` in this folder first. |
| Port 8000 is already in use | Close the other NyayaBandhu console window, then start again. |
| Browser does not open | Open `http://127.0.0.1:8000/admin` manually. |

The installer has been checked for script structure and application imports on
Linux. Windows execution still needs verification on a Windows machine.
On 5 November 2026, a Windows test completed package installation but failed
at the final Python import check because PowerShell removed nested quotes in
the `-c` argument. The version and import checks now use commands without
nested quotes. The corrected installer still needs a Windows rerun.
On 9 November 2026, another Windows test showed that Python's installer exited
successfully but its executable was not in the custom application folder. The
installer now uses Python's documented per-user default location and searches
for the interpreter after installation. This change also needs a Windows rerun.

## Update an installed copy (v5 onward)

Close the NyayaBandhu server, then double-click **update.bat** in the installed
folder. Internet access is required. The updater downloads the latest published
Windows release and its SHA-256 checksum from
`RihaanBH-1810/NyayaBandhu` on GitHub. It verifies the checksum, checks the package,
backs up review stores, updates application files and dependencies, and checks
application imports. Start the app again with `start.bat`.

Uploaded PDFs, local catalog entries, review stores, and the Python environment
are preserved. Conflicting source PDFs stop the update. Replaced application files
and review stores are backed up in `update-backups/<timestamp>/`. If installation
fails, application files are restored; dependency installation may still need
repair with `install.bat`. Backups include review data: retain them securely and
remove old backups when no longer needed. Stop the server before every update.

The default feed requires a publicly accessible repository/release. A private
repository will not download anonymously; publish releases in an accessible
repository before handing out the installer. To use a different GitHub-compatible
HTTPS release feed, create `update-settings.json` in the installed folder:

```json
{"release_feed":"https://api.github.com/repos/OWNER/REPOSITORY/releases/latest"}
```

This setting survives updates. You can check availability without installing:

```bat
.venv\Scripts\python.exe scripts\update_windows.py --check
```

The lawyer only needs the new v5 installer once. Older installed copies do not
contain the updater; install v5 into the same application folder to add it.
Future releases are fetched by `update.bat`, so there is no need to send the ZIP
manually each time. An update is available only after a release is published;
unpublished commits on main are not downloaded.

## Publish future updates

Push the release changes to GitHub. Run **Actions → Publish Windows release**
with a new version such as `v5.1`, or push a `v*` tag. The workflow builds and
publishes one `NyayaBandhu-Windows-<version>.zip` and its matching
`.zip.sha256` file. Those assets are required by the updater. Use a new version
for every release and test the package before directing users to update.

To build locally from a clean, committed checkout:

```sh
python scripts/build_windows_release.py --version v5 --output ../brief
```

The builder packages committed files, including the PDF catalog and source PDFs,
without developer environments, local review stores, or tests. `release.json`
inside the ZIP records its version and exact source commit. Downloaded release
checksums detect corruption; their trust comes from the HTTPS release host.
This updater has automated file preservation and rollback tests on Linux;
installation and update still need a complete Windows verification.
