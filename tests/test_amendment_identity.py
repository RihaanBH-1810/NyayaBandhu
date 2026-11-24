from source_corpus import legacy_pdf
from pathlib import Path

import pytest
import pymupdf

from akn_consolidator.service import Consolidator
from akn_consolidator.common import Q, parse, serialise
from webui import workspace as ui

ROOT = Path(__file__).resolve().parents[1]
AUTH = {'actor':'Reviewer','reason':'Identity check test'}


def fixture(name):
    return ((ROOT / f'out/amendment/eng/{name}.xml').read_bytes(),
            legacy_pdf(name).read_bytes())


def test_wrong_act_is_queued_without_registering(tmp_path):
    svc=Consolidator(tmp_path)
    base=svc.import_source((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                           (ROOT/'data/acts/2020/ka-0004-2020/karnataka-state-civil-services-regulation-of-transfer-of-teachers-act-2020__gazette__kan-eng.pdf').read_bytes(),'base',**AUTH)
    xml,pdf=fixture('Kannada_2024')
    result=svc.import_source(xml,pdf,'amendment',work_id=base['work_id'],revision=base['revision'],**AUTH)
    assert result['status']=='mismatch'
    assert len(svc.upload_checks(base['work_id']))==1
    assert not [s for s in svc.history(base['work_id'])['sources'] if s['kind']=='amendment']
    with pytest.raises(Exception,match='Only an unclear identity'):
        svc.confirm_upload(result['check_id'],base['revision'],'Reviewer','Correction',1,'Teachers Act')


def test_correct_act_registers(tmp_path):
    svc=Consolidator(tmp_path)
    base=svc.import_source((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                           (ROOT/'data/acts/2020/ka-0004-2020/karnataka-state-civil-services-regulation-of-transfer-of-teachers-act-2020__gazette__kan-eng.pdf').read_bytes(),'base',**AUTH)
    xml,pdf=fixture('First_ammendment')
    result=svc.import_source(xml,pdf,'amendment',work_id=base['work_id'],revision=base['revision'],**AUTH)
    assert result['source_id']
    assert not svc.upload_checks(base['work_id'])


def test_unclear_upload_needs_evidence_then_registers(tmp_path):
    svc=Consolidator(tmp_path)
    base=svc.import_source((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                           (ROOT/'data/acts/2020/ka-0004-2020/karnataka-state-civil-services-regulation-of-transfer-of-teachers-act-2020__gazette__kan-eng.pdf').read_bytes(),'base',**AUTH)
    xml,_=fixture('First_ammendment')
    root=parse(xml)
    for name in ('longTitle','preamble'):
        element=root.find('./'+Q('act')+'/'+Q(name))
        if element is not None:
            for child in element.iter():
                child.text=''
                child.tail=''
    pdf_doc=pymupdf.open(); page=pdf_doc.new_page(); page.insert_text((72,72),'Amendment source needs manual identity review')
    pdf=pdf_doc.tobytes();pdf_doc.close()
    pending=svc.import_source(serialise(root),pdf,'amendment',work_id=base['work_id'],revision=base['revision'],**AUTH)
    assert pending['status']=='unclear'
    svc.confirm_upload(pending['check_id'],base['revision'],'Reviewer','Checked source',1,'Teachers Act 2020')
    result=svc.complete_upload(pending['check_id'],base['revision'],**AUTH)
    assert result['source_id']


def test_base_provision_has_source_citation(tmp_path,monkeypatch):
    monkeypatch.setenv('NYAYA_CONSOLIDATION_DIR',str(tmp_path))
    svc=Consolidator(tmp_path)
    base=svc.import_source((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                           (ROOT/'data/acts/2020/ka-0004-2020/karnataka-state-civil-services-regulation-of-transfer-of-teachers-act-2020__gazette__kan-eng.pdf').read_bytes(),'base',**AUTH)
    result=ui.citations(base['expression']['id'],'sec_1')
    assert result['citations'][0]['source_id']==base['source_id']
