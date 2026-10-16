"""Line re-flow and hierarchy building."""
import pytest

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


def test_a_clause_after_a_proviso_rejoins_its_own_list():
    # Chandraguthi Act s.6: (a), a proviso, then (b)-(d). The proviso closes
    # (a), and (b) was being read as the start of a new list inside it.
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "6. Removal of member.-The State Government shall remove a member if,-\n"
        "(a) he becomes subject to any of the disqualifications in section 5:\n"
        "Provided that, no member shall be removed without a hearing.\n"
        "(b) he refuses to act; or\n"
        "(c) he absents himself from three meetings; or\n"
        "(d) he has abused his position:\n"
        "Provided that, no member shall be removed under this clause unheard.\n"
    )
    section = build(text).body[0]
    assert [(c.kind, c.num) for c in section.children] == [
        ("clause", "a"), ("proviso", ""), ("clause", "b"),
        ("clause", "c"), ("clause", "d"), ("proviso", ""),
    ]
    assert not section.children[1].children


def test_a_proviso_keeps_its_own_list_and_the_outer_list_resumes_after():
    # BBMP s.19(1): (a), a proviso with its own (i) and (ii), then (b).
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "19. Disqualifications.- (1) A person shall be disqualified if he,-\n"
        "(a) has been sentenced to imprisonment:\n"
        "Provided that,-\n"
        "(i) the offence is one which involves moral turpitude and\n"
        "(ii) such sentence has not been reversed; or\n"
        "(b) is so disqualified under any other law; or\n"
        "(c) holds an office of profit.\n"
    )
    subsec = build(text).body[0].children[0]
    assert [(c.kind, c.num) for c in subsec.children] == [
        ("clause", "a"), ("proviso", ""), ("clause", "b"), ("clause", "c"),
    ]
    assert [c.num for c in subsec.children[1].children] == ["i", "ii"]


@pytest.mark.parametrize("line", ["CHAPTER-I PRELIMINARY", "CHAPTER - II GENERAL",
                                  "CHAPTER III PRELIMINARY", "CHAPTER–IV FUND"])
def test_a_chapter_is_recognised_however_its_number_is_joined(line):
    # Chandraguthi Act: CHAPTER III beside CHAPTER-I, -II, -IV and -V.
    tok = Tokenizer().tokenize(line)[0]
    assert tok.kind == "chapter"
    assert tok.text in ("PRELIMINARY", "GENERAL", "FUND")


def test_hyphenated_chapters_group_their_sections():
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "CHAPTER-I\n"
        "PRELIMINARY\n"
        "1. Short title.- This Act may be called the X Act.\n"
        "CHAPTER III\n"
        "THE AUTHORITY\n"
        "2. Authority.- There shall be an Authority.\n"
        "CHAPTER-IV\n"
        "MISCELLANEOUS\n"
        "3. Rules.- The Government may make rules.\n"
    )
    doc = build(text)
    assert [(c.kind, c.num) for c in doc.body] == [
        ("chapter", "I"), ("chapter", "III"), ("chapter", "IV"),
    ]
    assert [[s.num for s in c.children] for c in doc.body] == [["1"], ["2"], ["3"]]
    assert not doc.preface or "CHAPTER" not in " ".join(doc.preface)


def test_a_long_heading_is_kept_when_subsection_one_follows():
    # Chandraguthi Act s.24: a 21-word heading naming another Act. Rejecting
    # it as "too long to be a heading" lost subsection (1) altogether.
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "24. Application of the Karnataka Public Premises (Eviction of "
        "unauthorized occupants) Act, 1974 (Karnataka Act 32 of 1974) to the "
        "Authority Premises.-(1) The State Government may by notification "
        "apply that Act.\n"
        "(2) On a notification being issued under sub-section (1), it shall apply.\n"
    )
    section = build(text).body[0]
    assert section.heading.endswith("to the Authority Premises")
    assert [c.num for c in section.children] == ["1", "2"]


def test_a_long_sentence_with_a_dash_is_still_not_a_heading():
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "5. Where the Authority is of the opinion that any building or work "
        "is in a state of disrepair and is likely to cause danger to the "
        "persons residing in the area.- it may order its repair.\n"
    )
    section = build(text).body[0]
    assert section.heading == ""


@pytest.mark.parametrize("line, heading", [
    ("372. Resignation and removal, – (1) The Authority may resign.",
     "Resignation and removal"),
    ("237. Power to allow certain projections;- (1) The Commissioner may allow.",
     "Power to allow certain projections"),
])
def test_a_heading_ended_with_a_comma_or_semicolon_before_subsection_one(line, heading):
    # BBMP ss.372 and 237. Without the heading, subsection (1) was lost and a
    # later "sub-section (1)" had nothing in its own section to point at.
    doc = build("An Act to do things.\nBe it enacted as follows:-\n" + line + "\n")
    section = doc.body[0]
    assert section.heading == heading
    assert [c.num for c in section.children] == ["1"]


def test_a_comma_dash_without_subsection_one_does_not_make_a_heading():
    # ",-" ends ordinary sentences all the time.
    text = (
        "An Act to do things.\n"
        "Be it enacted as follows:-\n"
        "2. In this Act, unless the context otherwise requires,-\n"
        "(a) \"Act\" means this Act;\n"
    )
    section = build(text).body[0]
    assert section.heading == ""
