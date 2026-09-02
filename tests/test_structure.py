"""Line re-flow and hierarchy building."""
from akn_parser.normalize import TextNormalizer
from akn_parser.structure import Tokenizer, TreeBuilder


def build(text):
    return TreeBuilder().build(Tokenizer().tokenize(TextNormalizer().run(text)))


def reflow(text):
    return TextNormalizer().run(text).split("\n")


def test_a_wrapped_sentence_is_rejoined():
    text = (
        "(2) It shall come into force on such date as the State Government may by\n"
        "notification, appoint.\n"
    )
    assert reflow(text) == [
        "(2) It shall come into force on such date as the State Government "
        "may by notification, appoint."
    ]


def test_a_proviso_after_a_colon_stays_a_separate_line():
    text = (
        "in the order of priority and from Zone B-to Zone-A:\n"
        "Provided that, posting of a teacher to Zone-C shall not apply.\n"
    )
    assert len(reflow(text)) == 2


def test_a_wrapped_citation_does_not_start_a_new_subsection():
    # BBMP s.11(1)(ii) wraps in the middle of "sub-section (1) of section 8".
    text = (
        "(ii) nominated by the Government under clause (b) of sub-section\n"
        "(1) of section 8 shall, be five years.\n"
    )
    lines = reflow(text)
    assert len(lines) == 1
    assert "sub-section (1) of section 8" in lines[0]


def test_an_inline_first_subsection_becomes_a_real_subsection():
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "1.Short title and commencement.-(1) This Act may be called the X Act.\n"
        "(2) It shall come into force at once.\n"
    )
    doc = build(text)
    section = doc.body[0]
    assert section.heading == "Short title and commencement"
    assert [c.num for c in section.children] == ["1", "2"]
    # The chapeau went into the subsection, not loose onto the section.
    assert not section.paragraphs


def test_a_marker_that_continues_a_letter_list_is_a_clause_not_a_roman():
    text = (
        "An Act to define things.\n"
        "Be it enacted as follows:-\n"
        "2. Definitions.-In this Act,-\n"
        '(h) "Specified posts" means posts of Cluster resource person;\n'
        '(i) "Teacher" means a person appointed to a post;\n'
        '(j) "Transfer" means posting of a teacher;\n'
    )
    section = build(text).body[0]
    assert [c.num for c in section.children] == ["h", "i", "j"]
    assert {c.list_type for c in section.children} == {"alpha"}


def test_a_marker_that_opens_a_roman_list_is_read_as_roman():
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "5. Zonal transfers.-Every alternate year,-\n"
        "(i) every teacher who has not served ten years shall be transferred.\n"
        "(ii) if no vacancy is available, one may be created.\n"
    )
    section = build(text).body[0]
    assert [c.num for c in section.children] == ["i", "ii"]
    assert {c.list_type for c in section.children} == {"roman"}


def test_a_restarted_letter_list_nests_instead_of_rejoining_the_outer_one():
    # BBMP s.83(2): clauses (a),(b); (b) has sub-clauses (i)-(iii); (iii)
    # opens a fresh (a)-(b) list.  Rejoining the outer list would produce two
    # elements with the eId ...__cl_a.
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "83. Composition.- (1) There shall be a Ward Committee.\n"
        "(2) The Ward Committee shall consist of the following, namely:-\n"
        "(a) the Councillor representing the Ward;\n"
        "(b) ten other members, out of which there shall be,-\n"
        "(i) at least two members belonging to the Scheduled Castes;\n"
        "(ii) at least three women members; and\n"
        "(iii) at least two members representing Associations satisfying:-\n"
        "(a) its registered office shall be located within the ward;\n"
        "(b) it shall represent a majority of residents;\n"
    )
    subsec2 = build(text).body[0].children[1]
    assert [c.num for c in subsec2.children] == ["a", "b"]
    clause_b = subsec2.children[1]
    assert [c.num for c in clause_b.children] == ["i", "ii", "iii"]
    nested = clause_b.children[2]
    assert [c.num for c in nested.children] == ["a", "b"]
    # ... and the nested list is a level deeper, so its eIds cannot collide.
    assert nested.children[0].kind == "point"


def test_provisos_attach_to_the_enclosing_provision_not_to_each_other():
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "20. Repeal and savings.-The old Act is hereby repealed:\n"
        "Provided that, such repeal shall not affect,-\n"
        "(a) anything done under the said Act; or\n"
        "(b) the previous operation of the said Act:\n"
        "Provided further that, the General Clauses Act shall apply.\n"
    )
    section = build(text).body[0]
    assert [c.kind for c in section.children] == ["proviso", "proviso"]
    assert [c.num for c in section.children[0].children] == ["a", "b"]
    assert not section.children[1].children
