"""Source intake checks for the two requested Act timelines."""
from pathlib import Path
from copy import deepcopy
import json

import pytest
from lxml import etree

from akn_parser.pipeline import ActParser
from akn_consolidator.common import parse, validate, canonical_hash
from akn_consolidator.engine import run, seed_identities, locate, apply_one
from akn_consolidator.extraction import extract
from akn_consolidator.service import Consolidator

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("source,number,sections", [
    ("data/v0s/kan_eng/tranfer_of_teachers.pdf", "4", 20),
    ("data/ammendments/First_ammendment.pdf", "27", 3),
    ("data/ammendments/Second_ammendment.pdf", "6", 13),
    ("data/ammendments/Teachers_2022.pdf", "32", 4),
    ("data/ammendments/Third_ammendment.pdf", "27", 7),
    ("data/v0s/eng/kannada_language_comprehensive_development_2022.pdf", "13", 31),
    ("data/ammendments/Kannada_2024.pdf", "7", 3),
])
def test_source_parses_to_valid_act_with_expected_sections(source, number, sections):
    result = ActParser().parse(str(ROOT / source))
    root = etree.fromstring(result.xml)
    work_uri = root.xpath('string(//*[local-name()="FRBRWork"]/*[local-name()="FRBRuri"]/@value)')
    assert result.report.ok and result.report.schema_valid
    assert work_uri.endswith('/' + number)
    assert len(root.xpath('//*[local-name()="section"]')) == sections


def test_kannada_amendment_candidates_apply_to_original_base():
    base = parse(ActParser().parse(str(ROOT / 'data/v0s/eng/kannada_language_comprehensive_development_2022.pdf')).xml)
    amendment = parse(ActParser().parse(str(ROOT / 'data/ammendments/Kannada_2024.pdf')).xml)
    body = extract(amendment, (ROOT / 'data/ammendments/Kannada_2024.pdf').read_bytes())
    assert len(body['coverage']) == 3
    assert [op['action'] for op in body['operations']] == [
        'effect', 'replace_provision', 'insert_provision', 'replace_provision',
    ]
    updated, report = run(base, [(op['id'], op) for op in body['operations']], seed_identities(base, 'test'), [])
    assert report['ok'] and validate(updated)['ok']
    assert updated.xpath('//*[@eId="sec_7__subsec_2__cl_a__subcl_vii-a"]')
    replacement = ''.join(updated.xpath('//*[@eId="sec_17__subsec_6"]')[0].itertext())
    assert '60% in Kannada language' in replacement
    assert replacement.strip().endswith('upper half of the name board')
    assert 'name board"' not in replacement


def test_teachers_2022_proposes_reviewable_double_proviso_substitution():
    amendment = parse(ActParser().parse(str(ROOT / 'data/ammendments/Teachers_2022.pdf')).xml)
    body = extract(amendment, (ROOT / 'data/ammendments/Teachers_2022.pdf').read_bytes())
    assert len(body['coverage']) == 4
    assert len(body['operations']) == 11
    assert not any(op['action'] == 'blocked' for op in body['operations'])
    assert [op['action'] for op in body['operations'] if op['id'].startswith('sec_3_op_')][:3] == [
        'omit_provision', 'omit_provision', 'insert_provision',
    ]
    predecessor = parse((ROOT / 'tests/fixtures/consolidation/Second.xml').read_bytes())
    candidates = [(op['id'], op) for op in body['operations']]
    updated, report = run(predecessor, candidates, seed_identities(predecessor, 'test'), [])
    assert report['ok'] and validate(updated)['ok']
    provisos = updated.xpath('//*[@eId="sec_7__subsec_1"]/*[local-name()="proviso"]')
    assert len(provisos) == 5
    assert 'Kalyana Karnataka Region' in ''.join(provisos[-1].itertext())


def test_all_four_teachers_amendments_can_form_a_reviewed_sequence(tmp_path):
    """Technical fixture dates and approvals do not represent legal approval."""
    service = Consolidator(tmp_path)
    actor = {'actor': 'Technical fixture', 'reason': 'Sequence regression only'}
    base = service.import_source(
        (ROOT / 'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
        (ROOT / 'data/v0s/kan_eng/tranfer_of_teachers.pdf').read_bytes(), 'base', **actor)
    work = base['work_id']
    approved = service.approve(base['expression']['id'], base['revision'],
                               base['expression']['xml_hash'], **actor)
    parent = approved['expression']
    reviews = json.loads((ROOT / 'tests/fixtures/consolidation/reviews.json').read_text())
    for name, stem, day in [
        ('First', 'First_ammendment', '2021-04-29'),
        ('Second', 'Second_ammendment', '2022-01-18'),
        ('Teachers_2022', 'Teachers_2022', '2022-10-13'),
        ('Third', 'Third_ammendment', '2026-04-10'),
    ]:
        imported = service.import_source(
            (ROOT / f'out/amendment/eng/{stem}.xml').read_bytes(),
            (ROOT / f'data/ammendments/{stem}.pdf').read_bytes(),
            'amendment', work_id=work, revision=approved['revision'], **actor)
        extracted = service.extract(imported['source_id'], imported['revision'], **actor)
        if name in reviews:
            body = deepcopy(reviews[name])
        else:
            body = deepcopy(extracted['manifest']['body'])
            body.update(identity_confirmed=True, date_confirmed=True,
                        effective_date=day,
                        date_evidence='TEST ASSUMPTION: at once; publication date')
            for operation in body['operations']:
                operation['review_status'] = 'accepted'
        if name == 'Third':
            # The old demo fixture binds to a predecessor without the 2022
            # amendment. Rebind every target to the newly staged predecessor.
            tree = parse(service.expression_xml(parent['id']))
            identities = dict(parent['body']['identities'])
            tombstones = list(parent['body']['tombstones'])
            for operation in body['operations']:
                if operation.get('target'):
                    target = locate(tree, operation['target'])
                    operation['expected_hash'] = canonical_hash(target)
                    if 'target_identity' in operation:
                        operation['target_identity'] = identities[target.get('eId')]
                apply_one(tree, operation, identities, tombstones,
                          f"{extracted['manifest']['id']}:2:{operation['id']}")
        reviewed = service.review(extracted['manifest']['id'], body,
                                  extracted['revision'], 1, **actor)
        preview = service.preview(work, parent['id'], day)
        assert preview['ok'], preview.get('conflicts')
        applied = service.apply(work, parent['id'], day, reviewed['revision'],
                                preview['preview_hash'], **actor)
        approved = service.approve(applied['expression']['id'], applied['revision'],
                                   applied['expression']['xml_hash'], **actor)
        parent = approved['expression']
    assert validate(parse(service.expression_xml(parent['id'])))['ok']
    assert len(service.workspace(work)['sources']) == 5
    assert service.export(parent['id']).startswith(b'PK')


def test_kannada_pair_cms_review_preview_and_export(tmp_path):
    """A synthetic date exercises the gate; actual commencement needs evidence."""
    service = Consolidator(tmp_path)
    actor = {'actor': 'Technical fixture', 'reason': 'Kannada CMS regression only'}
    base = service.import_source(
        (ROOT / 'out/base_act/eng/kannada_language_comprehensive_development_2022.xml').read_bytes(),
        (ROOT / 'data/v0s/eng/kannada_language_comprehensive_development_2022.pdf').read_bytes(),
        'base', **actor)
    approved = service.approve(base['expression']['id'], base['revision'],
                               base['expression']['xml_hash'], **actor)
    imported = service.import_source(
        (ROOT / 'out/amendment/eng/Kannada_2024.xml').read_bytes(),
        (ROOT / 'data/ammendments/Kannada_2024.pdf').read_bytes(),
        'amendment', work_id=base['work_id'], revision=approved['revision'], **actor)
    extracted = service.extract(imported['source_id'], imported['revision'], **actor)
    body = deepcopy(extracted['manifest']['body'])
    body.update(identity_confirmed=True, date_confirmed=True,
                effective_date='2024-03-01',
                date_evidence='TEST ONLY: synthetic effective date')
    for operation in body['operations']:
        operation['review_status'] = 'accepted'
    reviewed = service.review(extracted['manifest']['id'], body,
                              extracted['revision'], 1, **actor)
    preview = service.preview(base['work_id'], approved['expression']['id'], '2024-03-01')
    assert preview['ok'], preview.get('conflicts')
    applied = service.apply(base['work_id'], approved['expression']['id'], '2024-03-01',
                            reviewed['revision'], preview['preview_hash'], **actor)
    final = service.approve(applied['expression']['id'], applied['revision'],
                            applied['expression']['xml_hash'], **actor)['expression']
    assert validate(parse(service.expression_xml(final['id'])))['ok']
    assert service.export(final['id']).startswith(b'PK')
