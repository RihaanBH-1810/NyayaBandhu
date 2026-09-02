"""
End-to-end checks against the Karnataka State Civil Services (Regulation of
Transfer of Teachers) Act, 2020 -- a bilingual gazette PDF whose English half
runs from page 10 to page 19.
"""
AKN = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"a": AKN}


def q(tag):
    return f"{{{AKN}}}{tag}"


# -- extraction and language ------------------------------------------

def test_only_the_english_pages_are_used(teachers):
    kept = [p.number for p in teachers.pages if p.kept]
    assert kept == list(range(9, 19))


def test_no_untagged_kannada_survives_into_the_output(teachers):
    # Kannada may appear, but only inside an element that declares it.
    assert teachers.report.foreign_residue == {}


def test_kannada_is_kept_and_tagged_rather_than_deleted(teachers_xml):
    # The notification reads "the translation of <Kannada title> in the English
    # language".  That title is the Act's own name, so it is preserved and
    # labelled rather than dropped.
    spans = teachers_xml.findall(f".//{q('span')}[@{{{XML_NS}}}lang]")
    assert spans
    tags = {s.get(f"{{{XML_NS}}}lang") for s in spans}
    assert tags <= {"kn", "kn-Latn-x-nudi", "kn-x-misencoded"}


def test_legacy_encoded_runs_declare_their_encoding(teachers_xml):
    # The Kannada on the English pages is Nudi: Kannada glyphs stored as
    # Latin-1 bytes.  The tag says so, so a consumer never mistakes it for
    # clean Kannada and a converter can find every run by XPath.
    legacy = teachers_xml.findall(
        f".//{q('span')}[@{{{XML_NS}}}lang='kn-Latn-x-nudi']"
    )
    assert legacy
    assert "PÀ£ÁðlPÀ" in "".join(legacy[0].itertext())


def test_the_kannada_title_is_recorded_as_a_work_level_alias(teachers_xml):
    aliases = teachers_xml.findall(f".//{q('FRBRWork')}/{q('FRBRalias')}")
    langs = [a.get(f"{{{XML_NS}}}lang") for a in aliases]
    assert None in langs                      # the English title
    assert "kn-Latn-x-nudi" in langs          # the enacting-language title


# -- schema and identifiers -------------------------------------------

def test_the_document_is_valid_akoma_ntoso(teachers):
    assert teachers.report.schema_valid is True, teachers.report.schema_errors


def test_every_eid_is_unique_and_conformant(teachers):
    assert teachers.report.duplicate_eids == []
    assert teachers.report.malformed_eids == []


def test_no_reference_dangles(teachers):
    assert teachers.report.dangling_refs == []


def test_every_citation_resolved(teachers):
    assert teachers.report.unresolved_citations == []


# -- metadata ---------------------------------------------------------

def test_frbr_identifiers_come_from_the_document(teachers):
    m = teachers.meta
    assert m.jurisdiction == "in-ka"
    assert m.number == "4"
    assert m.work_date == "2020-03-26"          # assent
    assert m.expression_date == "2020-03-27"    # first publication
    assert m.language == "eng"
    assert m.work_uri == "/akn/in-ka/act/2020-03-26/4"
    assert m.expression_uri == "/akn/in-ka/act/2020-03-26/4/eng@2020-03-27"


def test_meta_children_are_in_schema_order(teachers_xml):
    meta = teachers_xml.find(f".//{q('meta')}")
    order = [child.tag.split("}")[1] for child in meta]
    expected = ["identification", "publication", "classification", "lifecycle",
                "workflow", "analysis", "temporalData", "references", "notes",
                "proprietary", "presentation"]
    assert order == sorted(order, key=expected.index)


# -- structure --------------------------------------------------------

def test_all_twenty_sections_are_present(teachers_xml):
    nums = [s.find(q("num")).text for s in teachers_xml.findall(f".//{q('section')}")]
    assert nums == [f"{n}." for n in range(1, 21)]


def test_front_matter_is_split_into_preface_preamble_and_body(teachers_xml):
    assert teachers_xml.find(f".//{q('longTitle')}") is not None
    assert teachers_xml.find(f".//{q('recital')}") is not None
    formula = teachers_xml.find(f".//{q('formula')}")
    assert formula is not None and formula.get("name") == "enactingFormula"
    assert teachers_xml.find(f".//{q('conclusions')}") is not None


def test_a_provision_with_children_uses_intro_not_content(teachers_xml):
    # AKN allows either <content> or intro?/children/wrapUp?, never both.
    sec2 = teachers_xml.xpath('//a:section[@eId="sec_2"]', namespaces=NS)[0]
    tags = [c.tag.split("}")[1] for c in sec2]
    assert "intro" in tags and "content" not in tags


def test_a_leaf_provision_uses_content(teachers_xml):
    clause = teachers_xml.xpath('//a:clause[@eId="sec_2__cl_a"]', namespaces=NS)[0]
    tags = [c.tag.split("}")[1] for c in clause]
    assert "content" in tags and "intro" not in tags


def test_provisos_are_proviso_elements_nested_in_their_subsection(teachers_xml):
    provisos = teachers_xml.xpath(
        '//a:subsection[@eId="sec_7__subsec_1"]/a:proviso', namespaces=NS
    )
    assert [p.get("eId") for p in provisos] == [
        f"sec_7__subsec_1__proviso_{i}" for i in range(1, 6)
    ]


def test_a_proviso_carries_its_own_clauses(teachers_xml):
    clauses = teachers_xml.xpath(
        '//a:proviso[@eId="sec_20__proviso_1"]/a:clause', namespaces=NS
    )
    assert [c.get("eId") for c in clauses] == [
        f"sec_20__proviso_1__cl_{letter}" for letter in "abcd"
    ]


def test_the_ambiguous_marker_is_read_from_its_neighbours(teachers_xml):
    # "(i)" in section 2 follows "(h)", so it is the ninth letter clause.
    assert teachers_xml.xpath('//a:clause[@eId="sec_2__cl_i"]', namespaces=NS)
    # "(i)" in section 10(1) opens a roman list.
    assert teachers_xml.xpath(
        '//a:clause[@eId="sec_10__subsec_1__cl_i"]', namespaces=NS
    )


def test_defined_terms_are_tagged_and_declared_in_the_ontology(teachers_xml):
    defs = teachers_xml.findall(f".//{q('def')}")
    assert len(defs) == 12                       # clauses (a) to (l)
    term_ids = {t.get("eId") for t in teachers_xml.findall(f".//{q('TLCTerm')}")}
    for d in defs:
        assert d.get("refersTo")[1:] in term_ids


# -- schedule ---------------------------------------------------------

def test_the_schedule_is_an_attachment_holding_a_document(teachers_xml):
    att = teachers_xml.xpath('//a:attachment[@eId="att_1"]', namespaces=NS)[0]
    doc = att.find(q("doc"))
    assert doc is not None and doc.get("name") == "schedule"
    assert doc.find(q("meta")) is not None       # its own FRBR identity


def test_the_schedule_table_survives_the_page_break(teachers_xml):
    rows = teachers_xml.xpath("//a:attachment//a:table/a:tr", namespaces=NS)
    # Header, two group rows and sixteen cadre rows, spanning pages 18-19.
    assert len(rows) == 19
    last = rows[-1].findall(q("td"))[-1]
    assert "All Special Teachers" in "".join(last.itertext())


def test_a_citation_made_from_inside_the_schedule_names_its_component(teachers_xml):
    # A bare "#sec_2" inside the schedule would address the schedule itself.
    sub = teachers_xml.xpath("//a:attachment//a:subheading", namespaces=NS)[0]
    hrefs = [r.get("href") for r in sub.findall(q("ref"))]
    assert hrefs == [
        "/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main#sec_2",
        "/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main#sec_16",
    ]


# -- references -------------------------------------------------------

def test_a_citation_of_a_central_act_is_not_linked_to_this_act(teachers_xml):
    clause = teachers_xml.xpath(
        '//a:clause[@eId="sec_10__subsec_1__cl_ii"]', namespaces=NS
    )[0]
    text = "".join(clause.itertext())
    assert "section 2 of the Rights of persons with disabilities Act" in text
    assert clause.findall(f".//{q('ref')}") == []


def test_a_list_of_sections_produces_one_link_per_section(teachers_xml):
    intro = teachers_xml.xpath(
        '//a:subsection[@eId="sec_7__subsec_1"]/a:intro', namespaces=NS
    )[0]
    hrefs = [r.get("href") for r in intro.findall(f".//{q('ref')}")]
    assert hrefs == ["#sec_4", "#sec_5", "#sec_6"]
