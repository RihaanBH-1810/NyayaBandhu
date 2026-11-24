"""Canonical, citation-addressed source PDF corpus."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
CATALOG = DATA / 'catalog.json'
IDENTITY = re.compile(r'^ka-(\d{4})-(\d{4})$')
TOKEN = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def load():
    return json.loads(CATALOG.read_text())['sources']


def path_for(record):
    path = (DATA / record['path']).resolve()
    if not path.is_relative_to(DATA.resolve()):
        raise ValueError('Source path escapes data directory')
    return path


def list_pdfs(kind=None, subtree=None, data_root=None):
    data_root = Path(data_root) if data_root is not None else DATA
    rows = json.loads((data_root / 'catalog.json').read_text())['sources']
    if kind:
        rows = [r for r in rows if r['kind'] == kind]
    if subtree:
        rows = [r for r in rows if r['path'].startswith('acts/' + subtree.strip('/') + '/')]
    return [data_root / r['path'] for r in sorted(rows, key=lambda r:r['path'])]


def find_by_hash(raw):
    digest = hashlib.sha256(raw).hexdigest()
    return next((r for r in load() if r['sha256'] == digest), None)


def register(raw, *, act_id, title_slug, kind, language, variant='gazette', affected_acts=()):
    """Write one reviewed source and catalog row; return existing row for exact bytes."""
    match = IDENTITY.fullmatch(act_id)
    if not match or not TOKEN.fullmatch(title_slug) or not TOKEN.fullmatch(variant):
        raise ValueError('Use ka-NNNN-YYYY and lowercase hyphenated title/variant')
    if kind not in {'base', 'amendment'} or language not in {'eng','kan','kan-eng'}:
        raise ValueError('Invalid kind or language')
    if kind == 'amendment' and not affected_acts:
        raise ValueError('Select at least one affected Act')
    if any(not IDENTITY.fullmatch(x) for x in affected_acts):
        raise ValueError('Invalid affected Act ID')
    if not raw.startswith(b'%PDF'):
        raise ValueError('A PDF is required')
    year = match.group(2)
    rel = f'acts/{year}/{act_id}/{title_slug}__{variant}__{language}.pdf'
    digest = hashlib.sha256(raw).hexdigest()
    doc = json.loads(CATALOG.read_text())
    prior = next((r for r in doc['sources'] if r['sha256'] == digest), None)
    if prior:
        if prior['id'] != act_id or prior['kind'] != kind or prior['language'] != language:
            raise ValueError('Duplicate PDF already belongs to another catalog identity')
        if not set(affected_acts).issubset(prior['affected_acts']):
            raise ValueError('Duplicate PDF has different affected Acts; review its catalog entry')
        return prior, False
    if any(r['path'] == rel for r in doc['sources']):
        raise ValueError('This source name is already used; choose another variant')
    target = DATA / rel
    if target.exists():
        raise ValueError('Destination already exists')
    row = {'id':act_id,'kind':kind,'title':title_slug.replace('-',' ').title(),
           'language':language,'variant':variant,'path':rel,'sha256':digest,
           'affected_acts':list(affected_acts)}
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        stream.write(raw); temp = Path(stream.name)
    os.replace(temp,target)
    try:
        doc['sources'].append(row)
        with tempfile.NamedTemporaryFile(mode='w',dir=DATA,delete=False) as stream:
            json.dump(doc,stream,indent=2);stream.write('\n'); catalog_temp=Path(stream.name)
        os.replace(catalog_temp,CATALOG)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return row, True


def legacy_pdf(stem):
    """Resolve a pre-migration fixture stem to its canonical source path."""
    row = next((r for r in load() if Path(r.get('legacy_path','')).stem == stem), None)
    if row is None:
        raise FileNotFoundError(stem)
    return path_for(row)
