"""Source-specific regressions for general parser and stitching rules."""
from source_corpus import DATA, load
from akn_parser.pipeline import ActParser
from akn_consolidator.common import parse, validate
from akn_consolidator.extraction import extract
from akn_consolidator.engine import run, seed_identities, _normal_map


def source(act_id, language=None):
    row = next(r for r in load() if r['id'] == act_id and (language is None or r['language'] == language))
    pdf = DATA / row['path']
    return parse(ActParser().parse(str(pdf)).xml), pdf.read_bytes()


def test_uppercase_palace_definitions_are_targetable_and_amendment_applies():
    base, _ = source('ka-0014-2025')
    amendment, pdf = source('ka-0035-2025')
    assert base.xpath('//*[@eId="sec_2__cl_D"]')
    assert base.xpath('//*[@eId="sec_2__cl_F"]')
    operations = extract(amendment, pdf)['operations']
    updated, result = run(base, [(op['id'], op) for op in operations], seed_identities(base, 'test'), [])
    assert result['ok'] and validate(updated)['ok']


def test_sub_section_context_and_subclause_replacement():
    amendment, pdf = source('ka-0029-2022')
    operation = extract(amendment, pdf)['operations'][1]
    assert operation['target']['path'] == [['section', '7'], ['subsection', '3'], ['clause', 'c']]
    amendment, pdf = source('ka-0012-2023')
    operations = extract(amendment, pdf)['operations']
    assert not any(op['action'] == 'blocked' for op in operations)
    assert any(op['target']['path'][-1] == ['subclause', 'b'] for op in operations if op.get('target'))


def test_explicit_omissions_and_act37_contents_page():
    amendment, pdf = source('ka-0017-2024')
    operations = extract(amendment, pdf)['operations']
    targets = [op['target']['path'] for op in operations if op['action'] == 'omit_provision']
    assert [['section', '142'], ['subsection', '3']] in targets
    assert [['section', '142'], ['subsection', '2']] in targets
    assert [['section', '148']] in targets
    amendment, pdf = source('ka-0037-2024')
    operations = extract(amendment, pdf)['operations']
    assert operations[0]['action'] != 'blocked'
    assert _normal_map('under sub-section (2)')[0] == _normal_map('under sub-section(2)')[0]


def test_proviso_rules_and_spaced_section_suffix():
    amendment, pdf = source('ka-0017-2024')
    operations = extract(amendment, pdf)['operations']
    assert any(op['action'] == 'omit_provision' and op['target']['path'][-1] == ['proviso', '3'] for op in operations)
    assert any(op['action'] == 'replace_provision' and op['target']['path'][-1] == ['proviso', '2'] for op in operations)
    amendment, pdf = source('ka-0007-2025')
    operations = extract(amendment, pdf)['operations']
    assert any(op['action'] == 'replace_provision' and op['target']['path'][-1] == ['proviso', '7'] for op in operations)
    amendment, pdf = source('ka-0034-2025')
    operations = extract(amendment, pdf)['operations']
    assert any(op.get('target', {}).get('path', [])[:1] == [['section', '240A']] for op in operations)
    assert not any(op['action'] == 'blocked' for op in operations)
    amendment, pdf = source('ka-0037-2024')
    operations = extract(amendment, pdf)['operations']
    assert any(op['action'] == 'effect' and op['classification'] == 'other' for op in operations)


def test_quoted_insert_does_not_include_instruction_conjunction():
    from akn_consolidator.extraction import replacement_payload
    assert replacement_payload('inserted, namely:- "(d) Legal words."; and') == '(d) Legal words.'


def test_exact_cross_reference_substitution_preserves_surrounding_words():
    from lxml import etree
    from akn_consolidator.common import Q, text, Conflict
    from akn_consolidator.engine import _text_operation
    import pytest
    node = etree.Element(Q('p'), eId='p')
    node.text = 'Prefix under '
    ref = etree.SubElement(node, Q('ref'), eId='ref', href='#sec_2')
    ref.text = 'section (2)'
    ref.tail = ' and old words. Suffix'
    _text_operation(node, {'action':'text_replace', 'old':'under section (2) and old words.', 'new':'new words.'})
    assert text(node) == 'Prefix new words. Suffix'
    assert not list(node)
    node.text = 'Prefix '
    ref = etree.SubElement(node, Q('ref'), eId='ref', href='#sec_2')
    ref.text = 'section (2)'
    ref.tail = ' old words'
    with pytest.raises(Conflict):
        _text_operation(node, {'action':'text_replace', 'old':'(2) old words', 'new':'new'})


def test_bbmp_2022_exact_substitutions_apply_without_manual_slots():
    base, _ = source('ka-0053-2020', 'eng')
    amendment, pdf = source('ka-0029-2022')
    operations = extract(amendment, pdf)['operations']
    updated, result = run(base, [(op['id'], op) for op in operations], seed_identities(base, 'test'), [])
    assert result['ok'], result['conflicts']
    assert validate(updated)['ok']


def test_title_spacing_equivalence_keeps_original_offsets():
    from lxml import etree
    from akn_consolidator.common import Q, text
    from akn_consolidator.engine import _text_operation
    node = etree.Element(Q('longTitle'))
    etree.SubElement(node, Q('p')).text = 'An Act for Government Primary school sand Government High schools.'
    _text_operation(node, {'action':'text_replace', 'old':'Government Primary Schools and Government High Schools', 'new':'Schools and Colleges', 'whole_word':True})
    assert text(node) == 'An Act for Schools and Colleges.'


def test_explicit_every_occurrence_instruction_binds_inventory():
    from lxml import etree
    from akn_consolidator.common import Q, text, Conflict
    from akn_consolidator.engine import _text_operation
    import pytest
    node = etree.Element(Q('p'), eId='p')
    node.text = 'School and School'
    op = {'action':'text_replace', 'old':'School', 'new':'College', 'global':True, 'whole_word':True, 'count':None}
    with pytest.raises(Conflict):
        _text_operation(node, op)
    op['source'] = {'quote':'For the word "School", wherever it occurs, substitute "College".'}
    assert len(_text_operation(node, op)) == 2
    assert text(node) == 'College and College'
