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


# An Act with chapters, shaped like the Chandraguthi Act: section 24 has no
# subsection (1) of its own, section 18 in the same chapter does.
CHAPTERED = {
    "chp_I__sec_2": None, "chp_I__sec_12": None, "chp_I__sec_12__subsec_1": None,
    "chp_III__sec_18": None, "chp_III__sec_18__subsec_1": None,
    "chp_III__sec_24": None, "chp_III__sec_24__subsec_2": None,
}


def resolve_chaptered(text, context=""):
    r = CitationResolver(CHAPTERED)
    return r, [(s.kind, s.text, s.href) for s in r.markup(text, context)]


def test_a_relative_citation_does_not_wander_into_another_section_of_the_chapter():
    # Widening the search was meant to cover the enclosing *section*, but it
    # took the first eId component, which in a chaptered Act is the chapter.
    # Section 24(2)'s "sub-section (1)" then linked to section 18(1).
    r, segs = resolve_chaptered("issued under sub-section (1), the Act shall apply",
                                "chp_III__sec_24__subsec_2")
    assert hrefs(segs) == []
    assert r.warnings


def test_a_section_of_the_bharatiya_nyaya_sanhita_is_external():
    # Chandraguthi Act s.31. "Sanhita" names a code, and "2(28)" runs on
    # past what the chain pattern takes in before the "of".
    r, segs = resolve_chaptered(
        "public servants within the meaning of section 2(28) of Bharatiya "
        "Nyaya Sanhita, 2023.", "chp_V__sec_31")
    assert hrefs(segs) == []
    assert r.external == 1 and not r.warnings


def test_a_compact_citation_of_another_act_does_not_link_into_this_one():
    # The definition of "Government Educational Institution" in a school
    # education Act. "section 2(3) of the Karnataka Education Act, 1983" was
    # linked to section 2 of the Act citing it.
    r, segs = resolve_chaptered(
        "approved schools as defined under section 2(3) of the Karnataka "
        "Education Act, 1983 and Government Pre-University College", "chp_I__sec_2")
    assert hrefs(segs) == []
    assert r.external == 1 and not r.warnings


def test_a_long_rules_title_with_brackets_and_etc_is_still_external():
    # Same definition: the instrument's name is over 90 characters and has
    # "etc." in a bracket, which used to stop the search for "Rules".
    r, segs = resolve_chaptered(
        "as defined under sub-rule (5) of rule 2 of The Karnataka Department "
        "of School Education (Pre-University) (Academic, Registration, "
        "Administration and Grant-in-aid etc.) Rules, 2024; and", "chp_I__sec_2")
    assert hrefs(segs) == []
    assert r.external == 1 and not r.warnings


def test_an_act_named_in_the_next_sentence_does_not_make_a_citation_external():
    # The search for the instrument's name stops at the full stop, so the
    # Act in the second sentence does not claim "section 12".
    r, segs = resolve_chaptered(
        "under section 12 of the scheme approved by the Government. The "
        "Karnataka Municipal Corporations Act, 1976 shall not apply.", "chp_III__sec_18")
    assert hrefs(segs) == ["#chp_I__sec_12"]


def test_a_keyword_written_against_its_bracket_is_still_a_citation():
    # Chandraguthi Act s.19(2): "sub section(1) of section 12".
    _, segs = resolve_chaptered("Subject to the provisions of sub section(1) of "
                                "section 12, on and from", "chp_III__sec_19")
    assert hrefs(segs) == ["#chp_I__sec_12__subsec_1"]


def test_the_year_of_a_set_of_rules_is_not_a_rule_number():
    # Chandraguthi Act s.39: "... Endowments Rules 2002" read as "rule 200".
    r, segs = resolve_chaptered("and the Karnataka Hindu Religious Institutions "
                                "and Charitable Endowments Rules 2002, shall prevail")
    assert hrefs(segs) == []
    assert not r.warnings
