"""Build a clean Windows source installer ZIP from committed Git files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def build(version, output):
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise RuntimeError('Commit changes before building a release')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    raw = subprocess.check_output(['git', 'archive', 'HEAD'], cwd=ROOT)
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'NyayaBandhu-Windows-{version}.zip'
    with tarfile.open(fileobj=io.BytesIO(raw)) as source, ZipFile(target, 'w', ZIP_DEFLATED) as bundle:
        for member in source:
            if not member.isfile():
                continue
            if member.name.startswith(('tests/', 'docs/status/')):
                continue
            bundle.writestr('NyayaBandhu/' + member.name, source.extractfile(member).read())
        bundle.writestr('NyayaBandhu/release.json', json.dumps({'version':version, 'commit':commit}, indent=2)+'\n')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n')
    print(target)
    print('SHA256:', digest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, default=ROOT.parent/'brief')
    args = parser.parse_args()
    if not args.version or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in args.version):
        parser.error('Version must contain only letters, numbers, dots and hyphens')
    build(args.version, args.output.resolve())
