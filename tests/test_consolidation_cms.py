"""CMS-specific inspection and real HTTP route wiring."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
from akn_consolidator.common import Conflict, digest
from akn_consolidator.service import Consolidator
from webui.consolidation import router, page_router

REVIEWS = json.loads((ROOT / 'tests/fixtures/consolidation/reviews.json').read_text())
AUTH = {'actor':'CMS regression reviewer','reason':'Review workspace test'}


def setup_first(tmp_path):
    service = Consolidator(tmp_path)
    base = service.import_source((ROOT / 'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                                 (ROOT / 'data/v0s/kan_eng/tranfer_of_teachers.pdf').read_bytes(),
                                 'base', **AUTH)
    approved = service.approve(base['expression']['id'],base['revision'],base['expression']['xml_hash'],**AUTH)
    imported = service.import_source((ROOT / 'out/amendment/eng/First_ammendment.xml').read_bytes(),
                                     (ROOT / 'data/ammendments/First_ammendment.pdf').read_bytes(),
                                     'amendment',work_id=base['work_id'],revision=approved['revision'],**AUTH)
    extracted = service.extract(imported['source_id'],imported['revision'],**AUTH)
    return service,base['work_id'],approved['expression'],extracted


def test_staged_inspector_shows_inserted_target_and_stable_identity(tmp_path):
    service,work,base,extracted=setup_first(tmp_path)
    manifest=extracted['manifest'];body=deepcopy(REVIEWS['First'])
    body['operations'].append({
        'id':'sec_2_op_2','action':'text_replace','review_status':'pending',
        'target':{'eid':'sec_10__subsec_6'},'old':'onetime','new':'one time','count':1,
        'source':deepcopy(body['operations'][1]['source'])})
    result=service.inspect_instruction(manifest['id'],base['id'],body,'sec_2_op_2')
    assert result['target_eid']=='sec_10__subsec_6'
    assert result['occurrences'][0]['text']=='onetime'
    key=f"{manifest['id']}:{manifest['revision'] + 1}:sec_2_op_1"
    assert result['target_identity']==digest((key+':sec_10__subsec_6').encode())[:24]
    assert any(p['eid']=='sec_10__subsec_6' for p in result['provisions'])
    assert 'sec_10__subsec_6' in result['target_xml']
    body['operations'][0]['review_status']='pending'
    with pytest.raises(Conflict,match='preceding instruction'):
        service.inspect_instruction(manifest['id'],base['id'],body,'sec_2_op_2')


def test_cms_read_model_avoids_large_expression_bodies(tmp_path):
    service,work,base,extracted=setup_first(tmp_path)
    view=service.workspace(work)
    assert view['work']['id']==work
    assert len(view['sources'])==2 and len(view['manifests'])==1
    assert 'body' not in view['expressions'][0]
    assert view['expressions'][0]['validation']['ok']
    assert service.expression(base['id'])['body']['identities']


def test_unresolved_commencement_placeholder_is_not_confirmation(tmp_path):
    service,work,base,extracted=setup_first(tmp_path)
    body=deepcopy(extracted['manifest']['body'])
    body['date_confirmed']=True
    body['effective_date']='2021-04-29'
    body['date_evidence']='Commencement requires a recorded date determination'
    with pytest.raises(ValueError,match='actual commencement evidence'):
        service.review(extracted['manifest']['id'],body,extracted['revision'],1,**AUTH)


async def asgi_request(app,method,path,body=None):
    payload=json.dumps(body).encode() if body is not None else b''
    messages=[];sent=False
    async def receive():
        nonlocal sent
        if not sent:
            sent=True
            return {'type':'http.request','body':payload,'more_body':False}
        await asyncio.Event().wait()
    async def send(message): messages.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,
           'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','root_path':'',
           'headers':[(b'content-type',b'application/json')],'server':('test',80),'client':('test',123)}
    task=asyncio.create_task(app(scope,receive,send))
    # Periodic wakeups let this restricted runner complete Starlette worker calls.
    for _ in range(800):
        if task.done(): break
        await asyncio.sleep(.01)
    await asyncio.wait_for(task,timeout=.1)
    status=next(m['status'] for m in messages if m['type']=='http.response.start')
    content=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
    return status,content


def test_html_catalog_and_inspection_http_flow(tmp_path,monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path))
    app=FastAPI();app.include_router(router);app.include_router(page_router)
    status,html=asyncio.run(asgi_request(app,'GET','/consolidation'))
    assert status==200 and b'Amendment workspace' in html and b'consolidation.js' in html
    status,raw=asyncio.run(asgi_request(app,'GET','/consolidation/api/catalog'))
    catalog=json.loads(raw)
    assert 'base_act/eng/tranfer_of_teachers.xml' in catalog['base_xml']
    assert 'v0s/kan_eng/tranfer_of_teachers.pdf' in catalog['pdf']
    service,work,base,extracted=setup_first(tmp_path)
    status,html=asyncio.run(asgi_request(app,'GET',f'/consolidation/read/{base["id"]}'))
    assert status==200 and b'akn-document' in html and b'Approved expression' in html
    status,raw=asyncio.run(asgi_request(app,'GET',f'/consolidation/api/works/{work}/workspace'))
    assert status==200 and json.loads(raw)['work']['revision']==extracted['revision']
    manifest=extracted['manifest'];body=deepcopy(REVIEWS['First'])
    status,raw=asyncio.run(asgi_request(app,'POST',f'/consolidation/api/manifests/{manifest["id"]}/inspect',{
        'expression_id':base['id'],'operation_id':'sec_2_op_1','body':body}))
    result=json.loads(raw)
    assert status==200 and result['target_eid']=='sec_10__subsec_5'
    assert result['expected_hash'] and result['provisions']
