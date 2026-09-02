"""eId construction against the OASIS naming convention (akn-nc v1.0, s.5.4)."""
import pytest

from akn_parser.eids import (
    DuplicateEId,
    EIdAssigner,
    element_ref,
    is_conformant,
    normalise_num,
)
from akn_parser.structure import ActDocument, Node


def test_element_ref_uses_the_specified_abbreviations():
    assert element_ref("section") == "sec"
    assert element_ref("subsection") == "subsec"
    assert element_ref("clause") == "cl"
    assert element_ref("subclause") == "subcl"
    assert element_ref("chapter") == "chp"
    assert element_ref("attachment") == "att"
    # Elements with no listed abbreviation keep their full name.
    assert element_ref("proviso") == "proviso"
    assert element_ref("point") == "point"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("(1)", "1"),
        ("1.", "1"),
        ("(a)", "a"),
        ("(iv)", "iv"),
        ("12A.", "12A"),
        ("Art. 11.2 bis", "11-2bis"),   # the specification's own example
        ("", ""),
    ],
)
def test_normalise_num(raw, expected):
    assert normalise_num(raw) == expected


def test_levels_are_joined_by_a_double_underscore():
    section = Node("section", num="7")
    subsec = Node("subsection", num="1")
    clause = Node("clause", num="a")
    section.children.append(subsec)
    subsec.children.append(clause)

    doc = ActDocument(body=[section])
    EIdAssigner().assign(doc)

    assert section.eid == "sec_7"
    assert subsec.eid == "sec_7__subsec_1"
    assert clause.eid == "sec_7__subsec_1__cl_a"
    assert all(is_conformant(n.eid) for n in (section, subsec, clause))


def test_unnumbered_elements_are_counted_within_their_parent():
    section = Node("section", num="7")
    section.children.extend([Node("proviso"), Node("proviso"), Node("proviso")])
    EIdAssigner().assign(ActDocument(body=[section]))
    assert [c.eid for c in section.children] == [
        "sec_7__proviso_1",
        "sec_7__proviso_2",
        "sec_7__proviso_3",
    ]


def test_counters_restart_inside_each_parent():
    doc = ActDocument(body=[Node("section", num="6"), Node("section", num="7")])
    for section in doc.body:
        section.children.append(Node("proviso"))
    EIdAssigner().assign(doc)
    assert doc.body[0].children[0].eid == "sec_6__proviso_1"
    assert doc.body[1].children[0].eid == "sec_7__proviso_1"


def test_a_collision_is_an_error_not_a_renamed_element():
    # The old parser appended "__2" to duplicates, which both hid the broken
    # hierarchy that caused them and collided with the level separator.
    section = Node("section", num="7")
    section.children.extend([Node("subsection", num="1"), Node("subsection", num="1")])
    with pytest.raises(DuplicateEId):
        EIdAssigner().assign(ActDocument(body=[section]))


@pytest.mark.parametrize(
    "eid,ok",
    [
        ("sec_7", True),
        ("sec_7__subsec_1__cl_a", True),
        ("att_1__hcontainer_1__table_1__tr_2", True),
        ("sec_12A", True),
        ("sec-7-subsec-1", False),      # the old, non-conformant separator
        ("__sec_7", False),
        ("7", False),
    ],
)
def test_eid_syntax(eid, ok):
    assert is_conformant(eid) is ok
