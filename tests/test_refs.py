"""Citation detection and resolution."""
import pytest

from akn_parser.refs import CitationResolver

# A miniature index shaped like the Teachers Transfer Act.
INDEX = {
    "sec_2": None, "sec_5": None, "sec_6": None, "sec_7": None, "sec_10": None,
    "sec_16": None,
    "sec_5__cl_i": None, "sec_5__cl_ii": None,
    "sec_7__subsec_1": None, "sec_7__subsec_2": None,
    "sec_7__subsec_1__proviso_1": None, "sec_7__subsec_1__proviso_4": None,
    "sec_10__subsec_1": None, "sec_10__subsec_2": None, "sec_10__subsec_5": None,
    "sec_10__subsec_1__cl_i": None, "sec_10__subsec_1__cl_iv": None,
}


def resolve(text, context=""):
    r = CitationResolver(INDEX, ["att_1"])
    segments = r.markup(text, context)
    return r, [(s.kind, s.text, s.href) for s in segments]


def hrefs(segments):
    return [href for kind, _, href in segments if kind == "ref"]


def test_a_plain_section_citation_is_linked():
    _, segs = resolve("specified under section 7.")
    assert hrefs(segs) == ["#sec_7"]


def test_each_number_of_a_list_is_linked_separately():
    _, segs = resolve("transfers under sections 5 and 6 under this Act")
    assert hrefs(segs) == ["#sec_5", "#sec_6"]


def test_a_chain_resolves_to_its_innermost_target():
    _, segs = resolve(
        "as defined in clause (i) to (iv) of sub-section (1) of section 10."
    )
    assert hrefs(segs) == ["#sec_10__subsec_1__cl_i", "#sec_10__subsec_1__cl_iv"]


def test_a_citation_of_another_act_is_left_unlinked():
    # The previous parser matched a hard-coded list of statute names; this is
    # decided from the shape of the text instead.
    r, segs = resolve(
        "as defined in clause (r) of section 2 of the Rights of persons with "
        "disabilities Act, 2016 (Central Act 49 of 2016);"
    )
    assert hrefs(segs) == []
    assert r.external == 1


def test_another_acts_section_is_left_unlinked_even_when_the_number_exists():
    r, segs = resolve(
        "the provisions of section 6 of the Karnataka General Clauses Act, 1899"
    )
    assert hrefs(segs) == []
    assert r.external == 1


def test_a_relative_subsection_resolves_against_its_context():
    _, segs = resolve(
        "subject to any modification made under sub-section (2).",
        context="sec_7__subsec_1",
    )
    assert hrefs(segs) == ["#sec_7__subsec_2"]


def test_a_sibling_list_resolves_across_subsections():
    # Section 10(2) cites "clauses (i) to (iv)", which live in 10(1).
    _, segs = resolve(
        "The categories falling under clauses (i) to (iv) are eligible",
        context="sec_10__subsec_2",
    )
    assert hrefs(segs) == ["#sec_10__subsec_1__cl_i", "#sec_10__subsec_1__cl_iv"]


def test_sub_clause_and_clause_are_accepted_as_the_same_level():
    # The Act itself uses both spellings for the same roman list.
    _, segs = resolve("transferred under sub-clause (i) to Zone-C",
                      context="sec_5__cl_ii")
    assert hrefs(segs) == ["#sec_5__cl_i"]


def test_an_ordinal_proviso_reference_resolves():
    _, segs = resolve("the limit prescribed in the fourth proviso, shall not",
                      context="sec_7__subsec_1__proviso_5")
    assert hrefs(segs) == ["#sec_7__subsec_1__proviso_4"]


def test_the_schedule_points_at_the_attachment():
    _, segs = resolve("such other posts as specified in the Schedule;")
    assert hrefs(segs) == ["#att_1"]


def test_an_unresolvable_citation_is_reported_not_invented():
    r, segs = resolve("as provided in section 99 of this Act")
    assert hrefs(segs) == []
    assert r.warnings and "section 99" in r.warnings[0].citation


@pytest.mark.parametrize("text", ["this Act", "the said Act", "Zone-C"])
def test_non_citations_are_left_alone(text):
    _, segs = resolve(text)
    assert hrefs(segs) == []
