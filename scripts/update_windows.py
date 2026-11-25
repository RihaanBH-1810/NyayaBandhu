"""Update an installed workspace from a published HTTPS release. No Git required."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = 'https://api.github.com/repos/RihaanBH-1810/NyayaBandhu/releases/latest'
PROTECTED = {'.git', '.venv', 'consolidation-data', 'review-data', 'update-backups', 'python'}


def fetch(url):
    if not url.startswith('https://'):
        raise ValueError('Update downloads require HTTPS')
    with urlopen(Request(url, headers={'User-Agent': 'NyayaBandhu-Updater', 'Accept': 'application/json'}), timeout=90) as response:
        if not response.url.startswith('https://'):
            raise ValueError('Update redirected outside HTTPS')
        return response.read()


def release_urls(feed):
    release = json.loads(fetch(feed))
    assets = {a['name']: a['browser_download_url'] for a in release.get('assets', [])}
    names = [name for name in assets if name.startswith('NyayaBandhu-Windows-') and name.endswith('.zip')]
    if len(names) != 1 or names[0] + '.sha256' not in assets:
        raise ValueError('Release must contain one NyayaBandhu-Windows-*.zip and its .zip.sha256 asset')
    return assets[names[0]], assets[names[0] + '.sha256']


def unpack(archive, destination):
    with ZipFile(archive) as bundle:
        for item in bundle.infolist():
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename or ':' in item.filename
                    or not path.parts or path.parts[0] != 'NyayaBandhu'
                    or any(part in PROTECTED for part in path.parts)):
                raise ValueError('Unsafe release archive path: ' + item.filename)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Release archive contains a symbolic link')
        bundle.extractall(destination)
    staged = destination / 'NyayaBandhu'
    for required in ('release.json', 'requirements.txt', 'pyproject.toml', 'start.bat', 'webui/app.py'):
        if not (staged / required).is_file():
            raise ValueError('Incomplete release: ' + required)
    return staged


def apply_files(staged, installed, backup):
    """Overlay release files, merge catalogs, and record every replaced file."""
    changes = []
    try:
        for source in sorted(staged.rglob('*')):
            if not source.is_file():
                continue
            rel = source.relative_to(staged)
            if rel.parts[0] in PROTECTED or rel.name == 'update-settings.json':
                continue
            target = installed / rel
            payload = source.read_bytes()
            if rel.as_posix() == 'data/catalog.json' and target.exists():
                old = json.loads(target.read_text())
                new = json.loads(payload)
                paths = {r['path']: r for r in old['sources']}
                for row in new['sources']:
                    prior = paths.get(row['path'])
                    if prior and prior['sha256'] != row['sha256']:
                        raise ValueError('Source catalog conflict: ' + row['path'])
                    paths.setdefault(row['path'], row)
                old['sources'] = list(paths.values())
                payload = (json.dumps(old, indent=2) + '\n').encode()
            elif rel.parts[0] == 'data' and target.exists():
                # Catalog PDFs can contain local additions and must never be overwritten.
                if rel.suffix.lower() == '.pdf' and target.read_bytes() != payload:
                    raise ValueError('Existing source PDF differs: ' + str(rel))
                if rel.suffix.lower() == '.pdf':
                    continue
            existed = target.exists()
            if existed:
                saved = backup / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            changes.append((rel, existed))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    except Exception:
        rollback(installed, backup, changes)
        raise
    return changes


def rollback(installed, backup, changes):
    for rel, existed in reversed(changes):
        target = installed / rel
        if existed:
            shutil.copy2(backup / rel, target)
        else:
            target.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', help='GitHub-compatible releases API URL (HTTPS)')
    parser.add_argument('--check', action='store_true', help='Check availability without applying')
    args = parser.parse_args()
    settings = ROOT / 'update-settings.json'
    feed = args.feed or (json.loads(settings.read_text()).get('release_feed') if settings.exists() else None) or DEFAULT_FEED
    url, checksum_url = release_urls(feed)
    print('Available release:', url.rsplit('/', 1)[-1])
    if args.check:
        return
    if (ROOT / '.git').exists():
        raise ValueError('Use Git to update a source checkout; update.bat is for installed ZIP copies')
    with socket.socket() as connection:
        connection.settimeout(1)
        if connection.connect_ex(('127.0.0.1', 8000)) == 0:
            raise ValueError('Close the running NyayaBandhu server before updating')
    with tempfile.TemporaryDirectory(prefix='nyaya-update-') as temporary:
        temp = Path(temporary)
        archive = temp / 'release.zip'
        raw = fetch(url)
        expected = fetch(checksum_url).decode().split()[0].lower()
        if len(expected) != 64 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Downloaded ZIP checksum does not match the release')
        archive.write_bytes(raw)
        staged = unpack(archive, temp / 'extracted')
        incoming = json.loads((staged / 'release.json').read_text())
        current = ROOT / 'release.json'
        if current.exists() and json.loads(current.read_text()) == incoming:
            print('This release is already installed.')
            return
        from datetime import datetime
        backup = ROOT / 'update-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True)
        # Server is stopped: preserve complete local review stores for recovery.
        for name in ('consolidation-data', 'review-data'):
            if (ROOT / name).exists():
                shutil.copytree(ROOT / name, backup / name)
        changes = apply_files(staged, ROOT, backup / 'application')
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-e', str(ROOT)], check=True)
            subprocess.run([sys.executable, '-c', 'import webui.workspace, akn_consolidator'], cwd=ROOT, check=True)
        except Exception:
            rollback(ROOT, backup / 'application', changes)
            raise RuntimeError('Application files restored after update failure. Dependencies may need repair with install.bat. Backup: ' + str(backup))
        print('Update complete. Start NyayaBandhu with start.bat.')
        print('Recovery backup:', backup)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Update failed:', error, file=sys.stderr)
        sys.exit(1)
