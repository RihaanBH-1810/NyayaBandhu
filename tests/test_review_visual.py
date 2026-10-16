"""Visual operations preserve AKN structure and review state."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException
from lxml import etree
from webui import review, review_editor as editor
from akn_parser.render import AKN_NS

TEACHERS = Path(__file__).resolve().parent.parent / 'out/base_act/eng/tranfer_of_teachers.xml'
BBMP = Path(__file__).resolve().parent.parent / 'out/base_act/eng/BBMP Act.xml'
Q = lambda tag: f'{{{AKN_NS}}}{tag}'


def act():
    return etree.parse(str(TEACHERS)).getroot()


def node(root, eid):
    return root.xpath('//*[@eId=$eid]', eid=eid)[0]


def test_text_edits_protect_inline_and_other_sections():
    root = act(); section = node(root, 'sec_2'); untouched = etree.tostring(node(root, 'sec_1'))
    fields = editor.prepare(section)['fields']
    field = next(f for f in fields if f['protected'] and any('def:' in p for p in f['protected']))
    paragraph = section
    for index in field['path']:
        paragraph = paragraph[index]
    protected = [(c.tag, dict(c.attrib), c.text) for c in paragraph]
    field['segments'][0] = 'Revised: ' + field['segments'][0]
    editor.edit(root, section, {'action': 'text', 'fields': [field]})
    assert paragraph.text.startswith('Revised: ')
    assert [(c.tag, dict(c.attrib), c.text) for c in paragraph] == protected
    assert etree.tostring(node(root, 'sec_1')) == untouched
    assert review._report(root)['ok']


@pytest.mark.parametrize('eid,kind', [('sec_1','section'), ('sec_1','subsection'), ('sec_2','clause'), ('sec_7__subsec_1','proviso')])
def test_add_supported_provisions(eid, kind):
    root = act(); original = etree.tostring(node(root, eid))
    description = editor.edit(root, node(root, eid), {'action':'add', 'child_type':kind})
    assert description.startswith('Added ')
    assert review._report(root)['ok']
    if kind == 'section':
        assert node(root, 'sec_21').findtext(Q('heading')) == 'New section'
        assert etree.tostring(node(root, eid)) == original
    else:
        assert etree.tostring(node(root, eid)) != original


def test_renumber_move_remove_and_reference_gate():
    root = act()
    with pytest.raises(ValueError, match='reference'):
        editor.edit(root, node(root, 'sec_7'), {'action':'renumber', 'number':'21'})
    editor.edit(root, node(root, 'sec_19'), {'action':'renumber', 'number':'21'})
    assert node(root, 'sec_21').findtext(Q('num')) == '21.'
    assert not root.xpath('//*[@eId="sec_19"]')
    assert review._report(root)['ok']
    root = act()
    editor.edit(root, node(root, 'sec_19'), {'action':'move', 'direction':'down'})
    assert node(root, 'sec_20').findtext(Q('heading')) == 'Repeal and savings' or node(root, 'sec_19').findtext(Q('heading')) == 'Repeal and savings'
    assert review._report(root)['ok']
    editor.edit(root, node(root, 'sec_20'), {'action':'remove'})
    assert review._report(root)['ok']


def test_add_child_to_leaf_preserves_text_and_inline_nodes():
    root = act(); section = node(root, 'sec_9')
    content = section.find(Q('content'))
    before = [(e.tag, e.text, {k:v for k,v in e.attrib.items() if k != 'eId'}) for e in content.iter()]
    editor.edit(root, section, {'action':'add', 'child_type':'subsection'})
    intro = section.find(Q('intro'))
    assert intro is not None and section.find(Q('content')) is None
    assert [(e.tag, e.text, {k:v for k,v in e.attrib.items() if k != 'eId'}) for e in intro.iter()][1:] == before[1:]
    assert review._report(root)['ok']


def test_table_cell_text_keeps_table_structure():
    root = etree.parse(str(BBMP)).getroot()
    p = root.xpath('//*[local-name()="table"]//*[local-name()="p"]')[0]
    section = next(a for a in p.iterancestors() if etree.QName(a).localname == 'section')
    before = [(e.tag, e.get('eId')) for e in section.iter() if etree.QName(e).localname in {'table','tr','th','td'}]
    field = next(f for f in editor.prepare(section)['fields'] if f['eid'] == p.get('eId'))
    field['segments'][0] += ' reviewed'
    editor.edit(root, section, {'action':'text', 'fields':[field]})
    assert p.text.endswith(' reviewed')
    assert [(e.tag, e.get('eId')) for e in section.iter() if etree.QName(e).localname in {'table','tr','th','td'}] == before
    assert review._report(root)['ok']


def test_revision_conflict_status_reset_and_out_immutable(tmp_path, monkeypatch):
    monkeypatch.setattr(review, 'STORE', tmp_path)
    original = TEACHERS.read_bytes()
    draft = review.create(review.Start(path='base_act/eng/tranfer_of_teachers.xml'))
    draft_id = draft['id']; eid = 'sec_1'
    provision = review.provision(draft_id, eid)
    field = provision['editor']['fields'][0]
    field['segments'][0] += ' revised'
    change = review.Change(revision=0, eid=eid, payload={'action':'text','fields':[field]})
    preview = review.preview(draft_id, change)
    assert preview['validation']['ok'] and review.get_draft(draft_id)['revision'] == 0
    saved = review.save_revision(draft_id, change)
    assert saved['revision'] == 1 and 'revised' in saved['diff']
    with pytest.raises(HTTPException) as exc:
        review.save_revision(draft_id, change)
    assert exc.value.status_code == 409
    review.approve(draft_id, review.Approval(revision=1, reviewer='Reviewer'))
    assert review.get_draft(draft_id)['status'] == 'approved'
    provision = review.provision(draft_id, eid)
    field = provision['editor']['fields'][0]; field['segments'][0] += ' again'
    review.save_revision(draft_id, review.Change(revision=1, eid=eid, payload={'action':'text','fields':[field]}))
    assert review.get_draft(draft_id)['status'] == 'draft'
    with pytest.raises(HTTPException): review.export(draft_id)
    assert TEACHERS.read_bytes() == original
