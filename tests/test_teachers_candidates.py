"""Unattended technical preparation never creates a legal approval."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from akn_consolidator.common import parse, validate
from akn_consolidator.service import Consolidator
from akn_consolidator import teachers_candidates as candidates

ROOT=Path(__file__).resolve().parents[1]


def test_four_distinct_valid_unapproved_drafts():
    raw,report=candidates.build_candidate_package()
    assert report['status']=='unapproved_technical_candidates'
    assert len({v['work_uri'] for v in report['versions']})==4
    assert [v['operation_count'] for v in report['versions']]==[3,23,11,11]
    with ZipFile(BytesIO(raw)) as package:
        assert package.read('profiles/teachers.json')
        for version in report['versions']:
            assert validate(parse(package.read(version['draft_file'])))['ok']


def test_source_registration_is_idempotent_and_pending(tmp_path):
    service=Consolidator(tmp_path)
    base=service.import_source((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                               (ROOT/'data/v0s/kan_eng/tranfer_of_teachers.pdf').read_bytes(),
                               'base','Technical preparer','Prepare pending sources')
    first=service.prepare_teachers_sources(base['work_id'],base['revision'],'Technical preparer','Prepare pending sources')
    again=service.prepare_teachers_sources(base['work_id'],first['revision'],'Technical preparer','Repeat safely')
    assert first['sources']==again['sources']
    assert first['revision']==again['revision']
    history=service.history(base['work_id'])
    assert len([s for s in history['sources'] if s['kind']=='amendment'])==4
    assert all(m['body']['status']=='needs_review' for m in history['manifests'])
    assert not any(e['approved_at'] for e in history['expressions'])


def test_changed_profile_is_rejected(monkeypatch):
    monkeypatch.setattr(candidates,'PROFILE_SHA256','0'*64)
    with pytest.raises(ValueError,match='profile changed'):
        candidates.build_candidate_package()
