"""Integrated visual review, real proposal rendering, and approved reader boundary."""
import asyncio
import json
from copy import deepcopy
from pathlib import Path
import sys

import pymupdf
import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from io import BytesIO

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from akn_consolidator.common import Conflict, parse
from akn_consolidator.service import Consolidator
from webui import workspace as ui, review_editor, akn_view, review
from webui.consolidation import router as consolidation_api
from test_consolidation_cms import AUTH, REVIEWS, setup_first, asgi_request


def base(svc):
    return svc.import_source((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                             (ROOT/'data/v0s/kan_eng/tranfer_of_teachers.pdf').read_bytes(),'base',**AUTH)


def edit_request(svc, record, expression=None, revision=None, **overrides):
    expression=expression or record['expression']
    node=parse(svc.expression_xml(expression['id'])).xpath('//*[@eId="sec_1"]')[0]
    fields=deepcopy(review_editor.prepare(node)['fields'])
    fields[1]['segments'][0]+=' Editorial test.'
    data={'revision':revision or record['revision'],'xml_hash':expression['xml_hash'],'eid':'sec_1',
          'payload':{'action':'text','fields':fields},
          'evidence':{'source_id':record['source_id'],'pdf_pages':[10],'quote':'Source wording for a regression test'},
          'preview':False,**AUTH,**overrides}
    return ui.VisualChange(**data)


def test_visual_base_revision_preview_approval_and_stale_writes(tmp_path):
    svc=Consolidator(tmp_path);record=base(svc);expr=record['expression'];source=svc.expression_xml(expr['id'])
    req=edit_request(svc,record,preview=True)
    preview=ui.edit_expression(svc,expr['id'],req)
    assert preview['validation']['ok'] and 'Editorial test.' in preview['after_html']
    assert svc.workspace(record['work_id'])['work']['revision']==record['revision']
    req.preview=False
    saved=ui.edit_expression(svc,expr['id'],req)
    assert svc.expression_xml(expr['id'])==source
    assert svc.expression(expr['id'])['invalidated_at']
    assert not saved['expression']['approved_at']
    assert saved['expression']['body']['identities']==expr['body']['identities']
    with pytest.raises(Conflict,match='Stale work revision'):
        ui.edit_expression(svc,expr['id'],req)
    approved=svc.approve(saved['expression']['id'],saved['revision'],saved['expression']['xml_hash'],**AUTH)
    assert approved['expression']['approved_at']
    assert b'Editorial test.' in svc.expression_xml(saved['expression']['id'])
    assert svc.export(saved['expression']['id']).startswith(b'PK')


def test_navigation_names_provision_levels_and_parent_context(tmp_path):
    svc=Consolidator(tmp_path);record=base(svc)
    root=parse(svc.expression_xml(record['expression']['id']))
    tree=akn_view.build_outline(root)
    assert tree[0].label == 'Section 1: Short title and commencement'
    assert tree[0].children[0].label == 'Subsection (1)'
    flat={row['eid']:row['label'] for row in ui.document(record['expression']['id'])['outline']}
    assert flat['sec_1__subsec_1'] == 'Section 1 › Subsection (1)'
    assert flat['sec_2__cl_a'] == 'Section 2 › Clause (a)'
    assert flat['sec_3__subsec_2__proviso_1'] == 'Section 3 › Subsection (2) › Proviso'
    assert flat['att_1__hcontainer_1'] == 'Schedule 1'
    assert {row['eid']:row['label'] for row in review._outline(root)}['sec_1__subsec_1'] == flat['sec_1__subsec_1']


def test_visual_edit_preserves_inline_nodes_and_reference_attributes(tmp_path):
    svc=Consolidator(tmp_path);record=base(svc)
    root=parse(svc.expression_xml(record['expression']['id']))
    node=root.xpath('//*[@eId="sec_2"]')[0]
    fields=deepcopy(review_editor.prepare(node)['fields'])
    field=next(f for f in fields if f['protected'])
    field['segments'][0]='Reviewed '+field['segments'][0]
    before=[(n.tag,dict(n.attrib),n.text) for n in node.iter() if n.tag.endswith(('}ref','}def','}span'))]
    req=edit_request(svc,record,eid='sec_2',payload={'action':'text','fields':fields})
    result=ui.edit_expression(svc,record['expression']['id'],req)
    after_root=parse(svc.expression_xml(result['expression']['id']))
    after=[(n.tag,dict(n.attrib),n.text) for n in after_root.xpath('//*[@eId="sec_2"]')[0].iter() if n.tag.endswith(('}ref','}def','}span'))]
    assert before==after and before


def test_reediting_a_correction_still_supersedes_the_approved_predecessor(tmp_path):
    svc=Consolidator(tmp_path);record=base(svc)
    approved=svc.approve(record['expression']['id'],record['revision'],record['expression']['xml_hash'],**AUTH)
    first=ui.edit_expression(svc,record['expression']['id'],edit_request(svc,record,revision=approved['revision']))
    second=ui.edit_expression(svc,first['expression']['id'],edit_request(svc,record,first['expression'],first['revision']))
    assert not svc.expression(record['expression']['id'])['invalidated_at']
    done=svc.approve(second['expression']['id'],second['revision'],second['expression']['xml_hash'],**AUTH)
    assert svc.expression(record['expression']['id'])['invalidated_at']
    assert svc.expression(first['expression']['id'])['invalidated_at']
    assert not done['expression']['invalidated_at']


def test_visual_structural_revision_records_new_identities_and_validates(tmp_path):
    svc=Consolidator(tmp_path);record=base(svc)
    result=ui.edit_expression(svc,record['expression']['id'],edit_request(svc,record,payload={'action':'add','child_type':'subsection'}))
    ids=result['expression']['body']['identities'];old=record['expression']['body']['identities']
    assert all(ids[k]==v for k,v in old.items())
    assert 'sec_1__subsec_3' in ids and result['validation']['ok']


def test_visual_requires_real_evidence_and_exact_version(tmp_path):
    svc=Consolidator(tmp_path);record=base(svc)
    with pytest.raises(ValueError,match='within the source'):
        ui.edit_expression(svc,record['expression']['id'],edit_request(svc,record,evidence={'source_id':record['source_id'],'pdf_pages':[100000],'quote':'test'}))
    with pytest.raises(Conflict,match='version changed'):
        ui.edit_expression(svc,record['expression']['id'],edit_request(svc,record,xml_hash='wrong'))
    assert len(svc.workspace(record['work_id'])['expressions'])==1


def test_canvas_replays_first_amendment_without_persisting_and_rejection_blocks_batch(tmp_path):
    svc,work,parent,extracted=setup_first(tmp_path);manifest=extracted['manifest'];body=deepcopy(REVIEWS['First'])
    original=svc.expression_xml(parent['id'])
    canvas=ui.make_canvas(svc,manifest['id'],ui.Canvas(expression_id=parent['id'],manifest_revision=manifest['revision'],body=body))
    insert=next(r for r in canvas['rows'] if r['action']=='insert_provision')
    assert any(p['label'].startswith('Section 10 › Subsection (5)') for p in canvas['provisions'])
    assert 'sec_10__subsec_6' in insert['after_html'] and 'sec_10__subsec_6' not in insert['before_html']
    assert '<ins>' in insert['after_diff']
    assert 'wording-inserted' in insert['after_html']
    assert svc.expression_xml(parent['id'])==original
    assert svc.workspace(work)['work']['revision']==extracted['revision']
    body['operations'][1].update(review_status='pending',review_decision='rejected',review_note='Check wording')
    reviewed=svc.review(manifest['id'],body,extracted['revision'],manifest['revision'],**AUTH)
    assert reviewed['manifest']['body']['status']=='needs_review'
    assert reviewed['manifest']['body']['operations'][1]['review_decision']=='rejected'
    with pytest.raises(Conflict,match='Unresolved'):
        svc.preview(work,parent['id'],body['effective_date'])
    with pytest.raises(Conflict,match='review changed'):
        ui.make_canvas(svc,manifest['id'],ui.Canvas(expression_id=parent['id'],manifest_revision=1,body=body))


@pytest.mark.parametrize('action', ['renumber','insert_provision'])
def test_canvas_includes_a_renumbered_section_or_new_sibling(tmp_path,action):
    svc,work,parent,extracted=setup_first(tmp_path);manifest=extracted['manifest']
    body=deepcopy(REVIEWS['First']);op=body['operations'][1]
    op.update(action=action,target={'eid':'sec_19'},new_number='21.',
              fragments=[{'tag':'section','num':'21.','heading':'Inserted section','text':'New sibling wording.'}])
    op.pop('expected_hash')
    canvas=ui.make_canvas(svc,manifest['id'],ui.Canvas(expression_id=parent['id'],manifest_revision=manifest['revision'],body=body))
    row=canvas['rows'][1]
    assert not row.get('conflict') and 'data-eid="sec_21"' in row['after_html']
    assert 'data-eid="sec_21"' not in row['before_html']
    if action=='insert_provision': assert 'New sibling wording.' in row['after_html']


def test_visual_base_flows_into_real_amendment_engine(tmp_path):
    svc=Consolidator(tmp_path);record=base(svc)
    saved=ui.edit_expression(svc,record['expression']['id'],edit_request(svc,record))
    approved=svc.approve(saved['expression']['id'],saved['revision'],saved['expression']['xml_hash'],**AUTH)
    imp=svc.import_source((ROOT/'out/amendment/eng/First_ammendment.xml').read_bytes(),(ROOT/'data/ammendments/First_ammendment.pdf').read_bytes(),'amendment',work_id=record['work_id'],revision=approved['revision'],**AUTH)
    ext=svc.extract(imp['source_id'],imp['revision'],**AUTH)
    review=svc.review(ext['manifest']['id'],deepcopy(REVIEWS['First']),ext['revision'],ext['manifest']['revision'],**AUTH)
    report=svc.preview(record['work_id'],approved['expression']['id'],'2021-04-29')
    assert report['ok']
    applied=svc.apply(record['work_id'],approved['expression']['id'],'2021-04-29',review['revision'],report['preview_hash'],**AUTH)
    assert b'Editorial test.' in svc.expression_xml(applied['expression']['id'])
    assert b'sec_10__subsec_6' in svc.expression_xml(applied['expression']['id'])
    with pytest.raises(Conflict,match='Approve the consolidated draft'):
        ui.edit_expression(svc,applied['expression']['id'],edit_request(svc,record,applied['expression'],applied['revision']))


def test_reader_only_lists_approved_versions_and_generates_pdf(tmp_path,monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path));svc=Consolidator(tmp_path);record=base(svc)
    assert ui.catalogue(public=True)==[]
    with pytest.raises(HTTPException): ui.document(record['expression']['id'],public=True)
    ap=svc.approve(record['expression']['id'],record['revision'],record['expression']['xml_hash'],**AUTH)
    assert len(ui.catalogue(public=True))==1
    d=ui.detail(record['work_id'],public=True)
    assert 'manifests' not in d and 'events' not in d
    pdf=ui.reader_pdf(record['expression']['id'])
    with pymupdf.open(stream=pdf.body,filetype='pdf') as doc:
        assert doc.page_count>0 and 'Short title' in ''.join(p.get_text() for p in doc)
    change=ui.edit_expression(svc,record['expression']['id'],edit_request(svc,record,revision=ap['revision']))
    svc.approve(change['expression']['id'],change['revision'],change['expression']['xml_hash'],**AUTH)
    with pytest.raises(HTTPException): ui.reader_xml(record['expression']['id'])
    assert [e['id'] for e in ui.detail(record['work_id'],public=True)['expressions']]==[change['expression']['id']]


def test_related_documents_and_issues_are_stored(tmp_path,monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path));svc=Consolidator(tmp_path);record=base(svc)
    ap=svc.approve(record['expression']['id'],record['revision'],record['expression']['xml_hash'],**AUTH)
    linked=ui.add_related(record['work_id'],ui.Related(revision=ap['revision'],title='Example linked source',kind='Rules',category='Education',document_date='2020-03-27',pdf_path='v0s/kan_eng/tranfer_of_teachers.pdf',**AUTH))
    assert ui.related_pdf(linked['id']).body==svc.source_artifact(record['source_id'],'pdf')
    issue=ui.report_issue(record['work_id'],ui.Issue(expression_id=record['expression']['id'],message='Please compare section 1 wording with the source.'))
    assert ui.detail(record['work_id'])['issues'][0]['id']==issue['id']
    assert len(ui.detail(record['work_id'],True)['related'])==1


def test_upload_pair_and_new_page_routes(tmp_path,monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path))
    async def upload_with_timer():
        task=asyncio.create_task(ui.upload(pdf=UploadFile(BytesIO((ROOT/'data/v0s/kan_eng/tranfer_of_teachers.pdf').read_bytes()),filename='base.pdf'),xml=UploadFile(BytesIO((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes()),filename='base.xml'),kind='base',actor=AUTH['actor'],reason=AUTH['reason'],work_id=None,revision=None))
        for _ in range(800):
            if task.done(): break
            await asyncio.sleep(.01)
        return await asyncio.wait_for(task,timeout=.1)
    result=asyncio.run(upload_with_timer())
    assert result['work_id']
    app=FastAPI();app.include_router(ui.pages);app.include_router(ui.api)
    for route in ('/','/admin','/library/search','/library/acts/'+result['work_id']):
        status,body=asyncio.run(asgi_request(app,'GET',route))
        assert status==200 and b'workspace.js' in body and b'gazette-frame' in body
    status,raw=asyncio.run(asgi_request(app,'GET','/workspace/api/works'))
    assert status==200 and b'TEACHERS' in raw


def test_schedule_table_cells_are_editable_without_changing_structure(tmp_path, monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR', str(tmp_path))
    svc=Consolidator(tmp_path);record=base(svc)
    original=parse(svc.expression_xml(record['expression']['id']))
    eid='att_1__hcontainer_1'
    info=ui.visual_provision(record['expression']['id'],eid)
    assert not info['structural'] and info['editor']['actions']==['text']
    assert eid in [p['eid'] for p in ui.document(record['expression']['id'])['outline']]
    fields=deepcopy(info['editor']['fields'])
    next(f for f in fields if f['tag']=='p')['segments'][0]+=' reviewed'
    saved=ui.edit_expression(svc,record['expression']['id'],edit_request(svc,record,eid=eid,payload={'action':'text','fields':fields}))
    revised=parse(svc.expression_xml(saved['expression']['id']))
    structure=lambda root:[(n.tag,dict(n.attrib)) for n in root.xpath('//*[@eId=$eid]',eid=eid)[0].iter()]
    assert structure(original)==structure(revised)
    assert saved['validation']['ok']
    with pytest.raises(ValueError,match='wording edits only'):
        ui.edit_expression(svc,saved['expression']['id'],edit_request(svc,record,saved['expression'],saved['revision'],eid=eid,payload={'action':'remove'}))


def test_http_review_apply_approve_export_and_repeated_editorial_correction(tmp_path,monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path))
    svc,work,parent,extracted=setup_first(tmp_path)
    app=FastAPI();app.include_router(ui.api);app.include_router(consolidation_api)
    def send(method,path,body=None):
        status,raw=asyncio.run(asgi_request(app,method,path,body))
        assert status==200,raw
        return json.loads(raw)
    manifest=extracted['manifest'];body=deepcopy(REVIEWS['First'])
    canvas=send('POST',f"/workspace/api/manifests/{manifest['id']}/canvas",{
        'expression_id':parent['id'],'manifest_revision':manifest['revision'],'body':body})
    assert not any(r.get('conflict') for r in canvas['rows'])
    reviewed=send('POST',f"/consolidation/api/manifests/{manifest['id']}/review",{
        **AUTH,'revision':extracted['revision'],'manifest_revision':manifest['revision'],'body':body})
    preview=send('POST',f'/consolidation/api/works/{work}/preview',{'parent_id':parent['id'],'effective_date':body['effective_date']})
    saved=send('POST',f'/consolidation/api/works/{work}/apply',{
        **AUTH,'revision':reviewed['revision'],'parent_id':parent['id'],'effective_date':body['effective_date'],'preview_hash':preview['preview_hash']})
    eid=saved['expression']['id']
    status,_=asyncio.run(asgi_request(app,'GET',f'/workspace/api/expressions/{eid}/xml'))
    assert status==400  # Drafts cannot be downloaded through the reader.
    approved=send('POST',f'/consolidation/api/expressions/{eid}/approve',{
        **AUTH,'revision':saved['revision'],'xml_hash':saved['expression']['xml_hash']})
    status,xml=asyncio.run(asgi_request(app,'GET',f'/workspace/api/expressions/{eid}/xml'))
    assert status==200 and b'sec_10__subsec_6' in xml
    record={'expression':approved['expression'],'revision':approved['revision'],
            'source_id':svc.workspace(work)['sources'][0]['id']}
    first=ui.edit_expression(svc,eid,edit_request(svc,record))
    second=ui.edit_expression(svc,first['expression']['id'],edit_request(svc,record,first['expression'],first['revision']))
    done=svc.approve(second['expression']['id'],second['revision'],second['expression']['xml_hash'],**AUTH)
    assert done['expression']['body']['kind']=='editorial_correction'
    assert done['expression']['body']['supersedes']==eid
    assert svc.expression(eid)['invalidated_at'] and svc.expression(first['expression']['id'])['invalidated_at']
    assert not svc.expression(parent['id'])['invalidated_at']
    assert svc.export(done['expression']['id']).startswith(b'PK')
