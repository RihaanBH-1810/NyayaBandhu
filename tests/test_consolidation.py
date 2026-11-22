"""Amendment rules, source preservation, transactional history, and CMS API."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest
from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
from akn_consolidator.common import Conflict, Q, canonical_hash, digest, parse, text, validate
from akn_consolidator.engine import apply_one, locate, occurrences, public_hits, run, seed_identities
from akn_consolidator.service import Consolidator

FIXTURES = ROOT / 'tests/fixtures/consolidation'
REVIEWS = json.loads((FIXTURES / 'reviews.json').read_text())
AUTH = {'actor':'Fixture reviewer (not legal attestation)','reason':'Regression test only'}
BASE = ROOT / 'out/base_act/eng/tranfer_of_teachers.xml'
PDF = ROOT / 'data/v0s/kan_eng/tranfer_of_teachers.pdf'


def approve(c, result):
    e = result['expression']
    return c.approve(e['id'], result['revision'], e['xml_hash'], **AUTH)


def start(directory):
    c = Consolidator(directory)
    result = c.import_source(BASE.read_bytes(), PDF.read_bytes(), 'base', **AUTH)
    return c, result['work_id'], approve(c, result)


def register(c, work, revision, name, ready=True):
    result = c.import_source((ROOT / f'out/amendment/eng/{name}_ammendment.xml').read_bytes(),
                             (ROOT / f'data/ammendments/{name}_ammendment.pdf').read_bytes(),
                             'amendment', work_id=work, revision=revision, **AUTH)
    result = c.extract(result['source_id'], result['revision'], **AUTH)
    manifest = result['manifest']
    if not ready: return result
    return c.review(manifest['id'], deepcopy(REVIEWS[name]), result['revision'], manifest['revision'], **AUTH)


def apply(c, work, result, parent, name):
    day = REVIEWS[name]['effective_date']
    preview = c.preview(work, parent['id'], day)
    assert preview['ok'], preview
    return c.apply(work, parent['id'], day, result['revision'], preview['preview_hash'], **AUTH)


@pytest.fixture(scope='module')
def chain(tmp_path_factory):
    c, work, result = start(tmp_path_factory.mktemp('chain'))
    versions = [result['expression']]
    for name in REVIEWS:
        result = register(c, work, result['revision'], name)
        result = approve(c, apply(c, work, result, versions[-1], name))
        versions.append(result['expression'])
    return c, work, versions


def test_full_teachers_chain_and_source_integrity(chain):
    c, work, versions = chain
    before = digest(BASE.read_bytes())
    assert [len(REVIEWS[n]['operations']) for n in REVIEWS] == [3, 23, 11]
    for name, version in zip(REVIEWS, versions[1:]):
        raw = c.expression_xml(version['id'])
        compared = parse(raw)
        for proprietary in compared.findall('.//' + Q('proprietary')):
            if len(proprietary) and all(child.tag.endswith('}legalEffect') for child in proprietary):
                proprietary.getparent().remove(proprietary)
        assert canonical_hash(compared) == canonical_hash(parse((FIXTURES / (name + '.xml')).read_bytes()))
        assert validate(parse(raw))['ok']
    root = parse(c.expression_xml(versions[-1]['id']))
    assert 'In case of a teacher who was transferred' in text(locate(root, {'eid':'sec_10__subsec_6'}))
    assert 'In case of a lecturer working' in text(locate(root, {'eid':'sec_10__subsec_7'}))
    assert 'Lecturer' in text(locate(root, {'eid':'sec_2__cl_cb'}))
    assert 'Critical Posts' in text(locate(root, {'eid':'sec_2__cl_ca'}))
    assert len(root.findall('.//' + Q('table'))) == 2
    assert 'Head Master' in text(locate(root, {'region':'schedule','label':'SCHEDULE-I'}))
    assert not root.xpath('//*[@eId="sec_10__subsec_1__cl_vii"]')
    assert '(vi)' in text(locate(root, {'eid':'sec_10__subsec_4'}))
    assert '(vii)' not in text(locate(root, {'eid':'sec_10__subsec_4'}))
    assert len(root.findall('.//' + Q('textualMod'))) == 32
    assert len(versions[-1]['body']['applied']) == 37
    for source in c.history(work)['sources']:
        assert digest(c.source_artifact(source['id'],'xml')) == source['xml_hash']
        assert digest(c.source_artifact(source['id'],'pdf')) == source['pdf_hash']
    assert digest(BASE.read_bytes()) == before


def test_untouched_subtrees_and_stable_identity(chain):
    c, _, v = chain
    roots = [parse(c.expression_xml(e['id'])) for e in v]
    for eid in ['sec_1', 'sec_11', 'sec_12', 'sec_13', 'sec_14', 'sec_15', 'sec_16']:
        # Whole-Act School substitution is deliberately limited to its inventory.
        assert canonical_hash(locate(roots[0],{'eid':eid})) == canonical_hash(locate(roots[-1],{'eid':eid}))
    assert v[2]['body']['identities']['sec_2__cl_ca'] == v[3]['body']['identities']['sec_2__cl_cb']
    assert v[2]['body']['identities']['sec_2__cl_ca'] != v[3]['body']['identities']['sec_2__cl_ca']
    assert v[2]['body']['identities']['sec_6'] == v[3]['body']['identities']['sec_6']
    assert any(t['eid']=='sec_10__subsec_1__cl_vii' for t in v[3]['body']['tombstones'])
    before = roots[0].xpath('//*[@xml:lang]',namespaces={'xml':'http://www.w3.org/XML/1998/namespace'})
    after = roots[-1].xpath('//*[@xml:lang]',namespaces={'xml':'http://www.w3.org/XML/1998/namespace'})
    assert [etree.tostring(e,with_tail=False) for e in before] == [etree.tostring(e,with_tail=False) for e in after]


def test_dates_history_export_and_restart(chain):
    c, work, v = chain
    reopened = Consolidator(c.store.directory)
    assert reopened.lookup(work,'2021-04-28')['expression']['id'] == v[0]['id']
    assert reopened.lookup(work,'2021-04-29')['expression']['id'] == v[1]['id']
    latest = reopened.lookup(work,'2026-04-10')
    assert latest['expression']['id'] == v[3]['id']
    assert latest['coverage']['complete_for_registered_sources']
    assert reopened.lookup(work,'2026-04-10',v[1]['approved_at'])['expression']['id'] == v[1]['id']
    bundle = reopened.export(v[3]['id'])
    assert bundle == reopened.export(v[3]['id'])
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert len(manifest['expression_history']) == 4
        assert len(manifest['instruction_history']) == 6
        assert digest(archive.read('consolidated.xml')) == v[3]['xml_hash']
        assert len([n for n in archive.namelist() if n.endswith('.pdf')]) == 4
    assert 'sec_2__cl_cb' in reopened.diff(v[2]['id'],v[3]['id'])


def test_unreviewed_dates_and_missing_extraction_block(tmp_path):
    c, work, result = start(tmp_path)
    base = result['expression']
    imported = c.import_source((ROOT/'out/amendment/eng/Second_ammendment.xml').read_bytes(),
                              (ROOT/'data/ammendments/Second_ammendment.pdf').read_bytes(), 'amendment',
                              work_id=work,revision=result['revision'],**AUTH)
    with pytest.raises(Conflict,match='Extract all'): c.preview(work,base['id'],'2022-01-18')
    extracted = c.extract(imported['source_id'],imported['revision'],**AUTH)
    assert extracted['manifest']['body']['effective_date'] is None
    with pytest.raises(Conflict,match='Unresolved'): c.preview(work,base['id'],'2022-01-18')
    coverage=c.lookup(work,'2026-10-17')['coverage']
    assert not coverage['complete_for_registered_sources'] and coverage['unresolved']


def test_stale_preview_duplicate_apply_hash_bound_approval(tmp_path):
    c, work, result = start(tmp_path); base=result['expression']
    result=register(c,work,result['revision'],'First')
    p=c.preview(work,base['id'],'2021-04-29')
    with pytest.raises(Conflict,match='Preview is obsolete'):
        c.apply(work,base['id'],'2021-04-29',result['revision'],'incorrect',**AUTH)
    drafted=c.apply(work,base['id'],'2021-04-29',result['revision'],p['preview_hash'],**AUTH)
    with pytest.raises(Conflict,match='Stale work revision'):
        c.apply(work,base['id'],'2021-04-29',result['revision'],p['preview_hash'],**AUTH)
    fresh=c.preview(work,base['id'],'2021-04-29')
    with pytest.raises(Conflict,match='already been applied'):
        c.apply(work,base['id'],'2021-04-29',drafted['revision'],fresh['preview_hash'],**AUTH)
    with pytest.raises(Conflict,match='Only a current approved'): c.export(drafted['expression']['id'])
    with pytest.raises(Conflict,match='exact XML hash'):
        c.approve(drafted['expression']['id'],drafted['revision'],base['xml_hash'],**AUTH)
    assert approve(c,drafted)['expression']['approved_by'] == AUTH['actor']


def test_instruction_revision_invalidates_descendants_and_keeps_known_history(tmp_path):
    c, work, result = start(tmp_path); base=result['expression']
    reviewed=register(c,work,result['revision'],'First')
    first=approve(c,apply(c,work,reviewed,base,'First'))
    second_review=register(c,work,first['revision'],'Second')
    second=approve(c,apply(c,work,second_review,first['expression'],'Second'))
    m=reviewed['manifest'];body=deepcopy(m['body']);body['operations'][1]['review_note']='Rechecked against the PDF'
    revised=c.review(m['id'],body,second['revision'],m['revision'],**AUTH)
    assert set(revised['stale'])=={first['expression']['id'],second['expression']['id']}
    with pytest.raises(Conflict): c.export(second['expression']['id'])
    assert c.lookup(work,'2023-01-01',second['expression']['approved_at'])['expression']['id']==second['expression']['id']
    assert c.lookup(work,'2023-01-01')['expression']['id']==base['id']
    assert not c.lookup(work,'2023-01-01')['coverage']['complete_for_registered_sources']
    assert c.preview(work,base['id'],'2021-04-29')['ok']


def test_approval_rechecks_new_source_coverage(tmp_path):
    c, work, result=start(tmp_path);base=result['expression']
    reviewed=register(c,work,result['revision'],'First')
    draft=apply(c,work,reviewed,base,'First')
    registered=register(c,work,draft['revision'],'Second',ready=False)
    with pytest.raises(Conflict,match='Unresolved'):
        c.approve(draft['expression']['id'],registered['revision'],draft['expression']['xml_hash'],**AUTH)


def test_atomic_conflict_leaves_parent_and_history_unchanged(tmp_path):
    c, work, result=start(tmp_path);base=result['expression']
    extracted=register(c,work,result['revision'],'First',ready=False);m=extracted['manifest']
    body=deepcopy(REVIEWS['First']);body['operations'][1]['target']={'eid':'missing'}
    reviewed=c.review(m['id'],body,extracted['revision'],1,**AUTH)
    before=c.expression_xml(base['id']);history=c.history(work)
    p=c.preview(work,base['id'],'2021-04-29'); assert not p['ok']
    with pytest.raises(Conflict,match='Application blocked'):
        c.apply(work,base['id'],'2021-04-29',reviewed['revision'],p['preview_hash'],**AUTH)
    assert c.expression_xml(base['id'])==before and c.history(work)==history


def test_concurrent_revision_writers(tmp_path):
    c, work, result=start(tmp_path)
    def import_once(_):
        other=Consolidator(tmp_path)
        try:
            return other.import_source((ROOT/'out/amendment/eng/First_ammendment.xml').read_bytes(),
                                       (ROOT/'data/ammendments/First_ammendment.pdf').read_bytes(),'amendment',
                                       work_id=work,revision=result['revision'],**AUTH)['source_id']
        except Conflict: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(x is not None for x in pool.map(import_once,range(2)))==1


def test_provenance_identity_and_missing_instruction_guards(tmp_path):
    c, work, result=start(tmp_path)
    extracted=register(c,work,result['revision'],'First',ready=False);m=extracted['manifest']
    variants=[]
    b=deepcopy(REVIEWS['First']);b['operations'].pop();variants.append((b,'silently deleted'))
    b=deepcopy(REVIEWS['First']);b['operations'][1]['source']['quote']='invented';variants.append((b,'provenance'))
    b=deepcopy(REVIEWS['First']);b['target_identity']['year']='1999';variants.append((b,'identity'))
    b=deepcopy(REVIEWS['First']);b['operations'][1]['action']='guess';variants.append((b,'Unknown instruction'))
    for body, message in variants:
        with pytest.raises(ValueError,match=message): c.review(m['id'],body,extracted['revision'],1,**AUTH)


def test_text_matches_preserve_inline_nodes_and_whitespace():
    root=parse(BASE.read_bytes()); ids=seed_identities(root,'test')
    target=locate(root,{'eid':'sec_10__subsec_4'})
    p=target.find('.//'+Q('p'));p.text=p.text.replace('categories falling','categories\n   falling')
    refs=[etree.tostring(r,with_tail=False) for r in p.findall(Q('ref'))]
    op={'action':'text_replace','target':{'eid':target.get('eId')},'old':'categories falling','new':'categories specified','count':1}
    edited, report=run(root,[('one',op)],ids,[])
    assert report['ok']
    assert [etree.tostring(r,with_tail=False) for r in locate(edited,op['target']).iter(Q('ref'))]==refs
    op['old']='cat';op['whole_word']=True
    assert not run(root,[('one',op)],ids,[])[1]['ok']


def test_protected_inventory_and_cross_inline_rejected_without_decision():
    root=parse(BASE.read_bytes());ids=seed_identities(root,'test')
    op={'action':'text_replace','target':{'eid':'sec_2__cl_i'},'old':'Schedule','new':'Schedule-I','count':1}
    assert 'protected' in run(root,[('one',op)],ids,[])[1]['conflicts'][0]['reason']
    op.update(occurrences=public_hits(occurrences(locate(root,op['target']),op['old'])),allow_protected=True)
    assert run(root,[('one',op)],ids,[])[1]['ok']
    op['occurrences'][0]['offset']+=1
    assert not run(root,[('one',op)],ids,[])[1]['ok']
    op={'action':'text_omit','target':{'eid':'sec_10__subsec_4'},'old':'and (vii)','count':1}
    assert 'crosses inline' in run(root,[('one',op)],ids,[])[1]['conflicts'][0]['reason']


def test_reference_gate_and_atomic_deferred_removal(chain):
    c, _, v=chain;root=parse(c.expression_xml(v[2]['id']));ids=v[2]['body']['identities']
    ops=deepcopy(REVIEWS['Third']['operations'])
    omission=next(o for o in ops if o['id']=='sec_6_op_2')
    reference=next(o for o in ops if o['id']=='sec_6_op_3')
    without=deepcopy(omission);without.pop('reference_updates')
    assert 'Incoming references' in run(root,[('omit',without)],ids,[])[1]['conflicts'][0]['reason']
    assert 'later inline omission' in run(root,[('omit',omission)],ids,[])[1]['conflicts'][0]['reason']
    output, report=run(root,[('omit',omission),('reference',reference)],ids,[])
    assert report['ok']
    assert not output.xpath('//*[@eId="sec_10__subsec_4__content__p_1__ref_2"]')
    assert output.xpath('//*[@eId="sec_10__subsec_4__content__p_1__ref_1"]')


def test_renumber_requires_reference_decisions_and_preserves_identity():
    root=parse(BASE.read_bytes());ids=seed_identities(root,'test')
    old='sec_10__subsec_1__cl_vi';new='sec_10__subsec_1__cl_viii'
    op={'action':'renumber','target':{'eid':old},'new_number':'(viii)'}
    assert not run(root,[('r',op)],ids,[])[1]['ok']
    op['reference_updates']=[{'eid':'sec_10__subsec_4__content__p_1__ref_1','old_href':'#'+old,'old_text':'(vi)','new_href':'#'+new,'new_text':'(viii)'}]
    edited,report=run(root,[('r',op)],ids,[])
    assert report['ok'] and report['identities'][new]==ids[old]
    assert locate(edited,{'eid':'sec_10__subsec_4__content__p_1__ref_1'}).get('href')=='#'+new
    op['new_number']='(vii)'
    assert not run(root,[('r',op)],ids,[])[1]['ok']


def test_editorial_correction_is_separate_and_supersedes_on_approval(tmp_path):
    c,work,result=start(tmp_path);base=result['expression']
    target={'eid':'sec_1'}
    inventory=c.inventory(base['id'],target,'Act, 2020')
    history=c.history(work)
    evidence={'source_id':history['sources'][0]['id'],'pdf_pages':[10],'quote':'Act, 2020'}
    operation={'action':'text_replace','target':target,'old':'Act, 2020','new':'Act, 2020','count':1,'expected_hash':inventory['expected_hash']}
    # A visible editorial change in a test copy, not a claimed correction to law.
    operation['new']='Act, 2020 (test)'
    draft=c.correct(base['id'],[operation],evidence,result['revision'],**AUTH)
    assert c.lookup(work,'2020-03-27')['expression']['id']==base['id']
    updated=approve(c,draft)
    assert c.lookup(work,'2020-03-27')['expression']['id']==updated['expression']['id']
    assert c.lookup(work,'2020-03-27',base['approved_at'])['expression']['id']==base['id']
    assert c.expression_xml(base['id'])==BASE.read_bytes() or canonical_hash(parse(c.expression_xml(base['id'])))==canonical_hash(parse(BASE.read_bytes()))
    with pytest.raises(Conflict): c.export(base['id'])


def test_artifact_corruption_is_detected(tmp_path):
    c,work,result=start(tmp_path)
    path=c.store.artifacts/result['expression']['xml_hash'];path.write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='integrity'): c.expression_xml(result['expression']['id'])


def test_cli_and_api(tmp_path,monkeypatch,capsys):
    from akn_consolidator.cli import main
    from webui import consolidation as api
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path))
    assert main(['--store',str(tmp_path),'import','--xml',str(BASE),'--pdf',str(PDF),'--kind','base','--actor','Tester','--reason','Smoke test'])==0
    result=json.loads(capsys.readouterr().out)
    assert api.works()[0]['id']==result['work_id']
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc: api.export(result['expression']['id'])
    assert exc.value.status_code==409
    approved=api.approve(result['expression']['id'],api.Approval(revision=result['revision'],actor='Tester',reason='API smoke',xml_hash=result['expression']['xml_hash']))
    assert approved['expression']['approved_at']
    assert api.export(result['expression']['id']).media_type=='application/zip'
    with pytest.raises(HTTPException): api.source_path('../../pyproject.toml','out','.xml')
    output=tmp_path/'export.zip'
    assert main(['--store',str(tmp_path),'export',result['expression']['id'],'--output',str(output)])==0
    assert zipfile.is_zipfile(output)
    assert main(['--store',str(tmp_path),'export',result['expression']['id'],'--output',str(output)])==2


def test_partial_commencement_and_earlier_batch_gate(tmp_path):
    c,work,result=start(tmp_path);base=result['expression']
    extracted=register(c,work,result['revision'],'First',ready=False);m=extracted['manifest']
    body=deepcopy(REVIEWS['First'])
    body['operations'][1]['effective_date']='2021-05-01'
    reviewed=c.review(m['id'],body,extracted['revision'],1,**AUTH)
    with pytest.raises(Conflict,match='earlier effective-date batch'):
        c.preview(work,base['id'],'2021-05-01')
    first=approve(c,apply(c,work,reviewed,base,'First'))
    assert len(first['expression']['body']['applied'])==2
    assert not parse(c.expression_xml(first['expression']['id'])).xpath('//*[@eId="sec_10__subsec_6"]')
    p=c.preview(work,first['expression']['id'],'2021-05-01');assert p['ok']
    later=approve(c,c.apply(work,first['expression']['id'],'2021-05-01',first['revision'],p['preview_hash'],**AUTH))
    assert len(later['expression']['body']['applied'])==3
    assert c.lookup(work,'2021-04-30')['expression']['id']==first['expression']['id']
    assert c.lookup(work,'2021-05-01')['expression']['id']==later['expression']['id']


def test_same_date_requires_distinct_instrument_sequence(tmp_path):
    c,work,result=start(tmp_path);base=result['expression']
    reviewed=register(c,work,result['revision'],'First')
    extracted=register(c,work,reviewed['revision'],'Second',ready=False);m=extracted['manifest']
    body=deepcopy(REVIEWS['Second']);body['effective_date']='2021-04-29';body['sequence']=1
    c.review(m['id'],body,extracted['revision'],1,**AUTH)
    with pytest.raises(Conflict,match='sequence is ambiguous'): c.preview(work,base['id'],'2021-04-29')


def test_late_discovered_earlier_instruction_invalidates_later_version(tmp_path):
    c,work,result=start(tmp_path);base=result['expression']
    reviewed=register(c,work,result['revision'],'First')
    first=approve(c,apply(c,work,reviewed,base,'First'))
    extracted=register(c,work,first['revision'],'Second',ready=False);m=extracted['manifest']
    body=deepcopy(REVIEWS['Second']);body['effective_date']='2021-04-28'
    revised=c.review(m['id'],body,extracted['revision'],1,**AUTH)
    assert first['expression']['id'] in revised['stale']
    assert c.lookup(work,'2021-05-01')['expression']['id']==base['id']


def test_global_match_inventory_is_required_and_exact():
    root=parse(BASE.read_bytes());ids=seed_identities(root,'test')
    op={'action':'text_replace','target':{'region':'act'},'old':'School','new':'School or College','whole_word':True,'global':True,'count':5}
    assert 'inventory' in run(root,[('g',op)],ids,[])[1]['conflicts'][0]['reason']
    inventory=public_hits(occurrences(locate(root,op['target']),'School',True))
    op.update(occurrences=inventory,count=len(inventory),allow_protected=True)
    edited,report=run(root,[('g',op)],ids,[])
    assert report['ok'] and 'School or College' in text(edited)
    op['count']+=1
    assert not run(root,[('g',op)],ids,[])[1]['ok']


def test_secure_xml_and_date_inputs(tmp_path):
    with pytest.raises(ValueError,match='DTD'): parse(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>')
    with pytest.raises(ValueError,match='Invalid XML'): parse(b'<a>')
    c,work,result=start(tmp_path)
    with pytest.raises(ValueError): c.lookup(work,'2021-1-1')
    with pytest.raises(ValueError,match='timezone'): c.lookup(work,'2021-01-01','2021-01-01T00:00:00')


def test_http_routes_without_server_socket(tmp_path,monkeypatch):
    """Exercise ASGI JSON validation and route dispatch without httpx or a socket."""
    import asyncio
    from fastapi import FastAPI
    from webui.consolidation import router
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path))
    app=FastAPI();app.include_router(router)
    async def request(method,path,body=None):
        payload=json.dumps(body).encode() if body is not None else b''
        messages=[];sent=False
        async def receive():
            nonlocal sent
            if not sent:
                sent=True
                return {'type':'http.request','body':payload,'more_body':False}
            await asyncio.Event().wait()
        async def send(message): messages.append(message)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http',
               'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'',
               'headers':[(b'content-type',b'application/json')],'server':('test',80),'client':('test',123)}
        # The restricted runner does not reliably wake asyncio's self-pipe
        # from worker threads. A timer keeps the real ASGI dispatch progressing.
        task=asyncio.create_task(app(scope,receive,send))
        for _ in range(1000):
            if task.done(): break
            await asyncio.sleep(.01)
        await asyncio.wait_for(task,timeout=.1)
        status=next(m['status'] for m in messages if m['type']=='http.response.start')
        content=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
        return status,json.loads(content)
    status,works=asyncio.run(request('GET','/consolidation/api/works'))
    assert status==200 and works==[]
    status,result=asyncio.run(request('POST','/consolidation/api/sources',{
        'kind':'base','xml_path':'base_act/eng/tranfer_of_teachers.xml','pdf_path':'v0s/kan_eng/tranfer_of_teachers.pdf',
        'actor':'API tester','reason':'ASGI smoke'}))
    assert status==200 and result['revision']==1
    status,_=asyncio.run(request('POST','/consolidation/api/expressions/'+result['expression']['id']+'/approve',{
        'revision':0,'xml_hash':result['expression']['xml_hash'],'actor':'Tester','reason':'Stale tab'}))
    assert status==409
    status,_=asyncio.run(request('POST','/consolidation/api/sources',{'kind':'base'}))
    assert status==422


def test_reimport_same_instrument_with_different_serialization_is_blocked(tmp_path):
    c,work,result=start(tmp_path)
    xml=(ROOT/'out/amendment/eng/First_ammendment.xml').read_bytes()
    pdf=(ROOT/'data/ammendments/First_ammendment.pdf').read_bytes()
    first=c.import_source(xml,pdf,'amendment',work_id=work,revision=result['revision'],**AUTH)
    changed=etree.tostring(parse(xml),pretty_print=True)
    with pytest.raises(Conflict,match='already registered'):
        c.import_source(changed,pdf,'amendment',work_id=work,revision=first['revision'],**AUTH)


def test_extraction_does_not_guess_wording_mismatches():
    from akn_consolidator.extraction import extract
    xml=parse((ROOT/'out/amendment/eng/Second_ammendment.xml').read_bytes())
    body=extract(xml,(ROOT/'data/ammendments/Second_ammendment.pdf').read_bytes())
    op=next(o for o in body['operations'] if o['id']=='sec_2_op_1')
    root=parse(BASE.read_bytes())
    _,report=run(root,[('exact',op)],seed_identities(root,'test'),[])
    assert not report['ok'] and 'found 0' in report['conflicts'][0]['reason']
    assert all(o['review_status']=='pending' for o in body['operations'])
    assert body['effective_date'] is None and not body['identity_confirmed']
