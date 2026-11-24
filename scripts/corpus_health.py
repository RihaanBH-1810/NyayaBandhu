"""Check every cataloged PDF and its normal review intake without altering workspaces."""
from __future__ import annotations
import hashlib
import json
import contextlib
import io
import tempfile
with contextlib.redirect_stdout(io.StringIO()):
    from akn_parser.pipeline import ActParser
    from akn_consolidator.service import Consolidator
from source_corpus import DATA, load


def audit():
    rows = load()
    results = []
    parsed = {}
    for row in rows:
        item = {'id': row['id'], 'path': row['path'], 'stage': 'parse'}
        try:
            pdf = DATA / row['path']
            raw = pdf.read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('PDF hash differs from catalog')
            result = ActParser().parse(str(pdf))
            if not result.report.ok:
                raise ValueError(result.report.summary())
            expected_number = str(int(row['id'][3:7]))
            if result.meta.number != expected_number or result.meta.year != row['id'][-4:]:
                raise ValueError('Parsed Act citation differs from catalog')
            if not result.meta.title:
                raise ValueError('Parsed title is empty')
            parsed[row['path']] = (result.xml, raw)
            item.update(stage='ready', title=result.meta.title)
        except Exception as exc:
            item.update(stage='failed', error=f'{type(exc).__name__}: {exc}')
        results.append(item)
    with tempfile.TemporaryDirectory() as folder:
        svc = Consolidator(folder)
        works = {}
        imported_amendments = set()
        for row, item in zip(rows, results):
            if item['stage'] != 'ready' or row['kind'] != 'base':
                continue
            if row['id'] in works:
                item['review'] = 'alternate edition available'
                continue
            try:
                xml, raw = parsed[row['path']]
                response = svc.import_source(xml, raw, 'base', 'Corpus audit', 'Intake check')
                works[row['id']] = response['work_id']
                item['review'] = 'base imported'
            except Exception as exc:
                item.update(stage='failed', error=f'Base import: {exc}')
        for row, item in zip(rows, results):
            if item['stage'] != 'ready' or row['kind'] != 'amendment':
                continue
            if row['id'] in imported_amendments:
                item['review'] = 'alternate edition available'
                continue
            targets = [target for target in row['affected_acts'] if target in works]
            item['missing_targets'] = [target for target in row['affected_acts'] if target not in works]
            if not targets:
                item.update(stage='failed', error='No principal Act in corpus')
                continue
            try:
                xml, raw = parsed[row['path']]
                work = works[targets[0]]
                revision = svc.workspace(work)['work']['revision']
                imported = svc.import_source(xml, raw, 'amendment', 'Corpus audit',
                                             'Intake check', work, revision)
                if imported.get('status'):
                    raise ValueError(f"Identity check: {imported['status']}")
                svc.extract(imported['source_id'], imported['revision'], 'Corpus audit', 'Intake check')
                item['review'] = 'amendment imported and extracted'
                imported_amendments.add(row['id'])
            except Exception as exc:
                item.update(stage='failed', error=f'Amendment intake: {exc}')
    return results


if __name__ == '__main__':
    report = audit()
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if any(row['stage'] == 'failed' for row in report) else 0)
