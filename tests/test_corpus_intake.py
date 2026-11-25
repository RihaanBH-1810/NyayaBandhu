"""Regression checks for the complete source corpus and live catalog intake."""
import asyncio
from source_corpus import load
from webui import workspace as ui


def test_catalog_intake_matches_documented_readiness():
    from corpus_health import audit
    report = audit()
    assert len(report) == len(load()) == 21
    failed = [row for row in report if row['stage'] != 'ready']
    # The newly supplied annotated compilation is retained as source evidence,
    # with a documented parser blocker, rather than counted as import-ready.
    assert len(failed) == 1 and failed[0]['id'] == 'ka-0014-1977'
    assert 'DuplicateEId' in failed[0]['error']
    assert all(row.get('review') for row in report if row['stage'] == 'ready')


def test_catalog_import_and_alternate_edition(tmp_path, monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR', str(tmp_path))
    rows = load()
    base = next(r for r in rows if r['id'] == 'ka-0013-2023' and r['variant'] == 'gazette')
    excerpt = next(r for r in rows if r['id'] == 'ka-0013-2023' and r['variant'] == 'excerpt')
    amendment = next(r for r in rows if r['id'] == 'ka-0007-2024' and r['language'] == 'kan-eng')
    common = dict(actor='Corpus tester', reason='Intake regression')
    async def call(body):
        task = asyncio.create_task(ui.import_catalog(body))
        for _ in range(1000):
            if task.done():
                break
            await asyncio.sleep(.01)
        return await asyncio.wait_for(task, timeout=.1)
    result = asyncio.run(call(ui.CatalogImport(source_path=base['path'], kind='base', **common)))
    assert result['work_id']
    alternate = asyncio.run(call(ui.CatalogImport(source_path=excerpt['path'], kind='base', **common)))
    assert alternate['status'] == 'alternate_source'
    linked = asyncio.run(call(ui.CatalogImport(source_path=amendment['path'], kind='amendment', work_id=result['work_id'], revision=result['revision'], **common)))
    assert linked['source_path'] == amendment['path']
    pdf = ui.catalog_pdf(excerpt['path'])
    assert pdf.body.startswith(b'%PDF')
