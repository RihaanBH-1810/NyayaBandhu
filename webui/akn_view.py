"""Akoma Ntoso XML -> view models for the browser viewer.

Nothing here duplicates ``akn_parser``. Structural checks (schema validity,
eId well-formedness, dangling references, untagged foreign script) are done
by ``akn_parser.validate.Validator``, exactly as the CLI report does; this
module only turns an already-valid document into HTML and Python data for
Jinja2 to lay out. It works from the finished XML tree, not from the parser's
internal ``ActDocument``, so it renders any conformant Akoma Ntoso 3.0
document, including ones this repository did not produce.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from functools import lru_cache

from lxml import etree

from akn_parser.render import AKN_NS, XML_LANG
from akn_parser.validate import Validator

#: Elements that hold child provisions (may themselves nest further
#: instances of the set) rather than only prose. Mirrors the hierarchy in
#: docs/akn-mapping.md; a tag absent from this set is treated as a plain
#: container and rendered without a numbered/headed label.
STRUCTURAL_TAGS = frozenset({
    "chapter", "part", "section", "subsection", "clause", "subclause",
    "point", "indent", "proviso", "hcontainer", "article", "paragraph",
    "subparagraph", "alinea", "division", "subdivision",
})

#: Containers that exist only to group other elements. Rendered as a plain
#: <div> with an optional label, never as a numbered provision.
_CONTAINER_LABELS = {
    "preface": "Preface",
    "preamble": "Preamble",
    "recitals": "Recitals",
    "recital": None,
    "formula": None,
    "longTitle": "Long title",
    "conclusions": "Conclusions",
    "attachments": "Schedules",
    "attachment": None,
    "doc": None,
    "mainBody": None,
    "body": None,
    "intro": None,
    "content": None,
    "wrapUp": None,
}

#: Direct children that a structural element's own label is built from, and
#: that must therefore not be rendered again as part of its body.
_LABEL_TAGS = {"num", "heading", "subheading"}


def _q(tag: str) -> str:
    return f"{{{AKN_NS}}}{tag}"


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def load(xml_path) -> etree._Element:
    """Parse *xml_path* and return the ``<akomaNtoso>`` root."""
    return etree.parse(str(xml_path)).getroot()


# -- the readable document view ---------------------------------------

def render_document_html(root: etree._Element) -> str:
    """Render the whole document body as reading-order HTML.

    Every element that carries an ``eId`` keeps it as the HTML element's
    ``id``, so a ``<ref href="#sec_7">`` becomes a same-page anchor link that
    jumps straight to section 7. That is the point of this view.
    """
    act = root.find(_q("act"))
    if act is None:
        return ""
    return "".join(
        _render_block(child) for child in act if _local(child.tag) != "meta"
    )


def _render_block(el: etree._Element) -> str:
    """Render one block-level element, dispatching on its local name.

    An element not named in any of the tables above is descended into rather
    than skipped, so a document using parts of the vocabulary this parser
    never emits still shows all of its text, just without special styling.
    """
    tag = _local(el.tag)
    if tag in _LABEL_TAGS:
        return ""  # consumed by the structural element that owns this label
    if tag == "p":
        return _render_p(el)
    if tag == "table":
        return _render_table(el)
    if tag == "crossHeading":
        eid = el.get("eId", "")
        return (f'<div id="{html.escape(eid)}" class="akn akn-crossHeading" '
                f'data-eid="{html.escape(eid)}">{html.escape(el.text or "")}</div>')
    if tag in STRUCTURAL_TAGS:
        return _render_structural(el, tag)
    if tag in _CONTAINER_LABELS:
        return _render_container(el, tag)
    # An element this viewer does not specifically know: descend rather than
    # drop it, so nothing silently disappears from the rendered document.
    return "".join(_render_block(child) for child in el)


def _render_container(el: etree._Element, tag: str) -> str:
    """Render a grouping element (``<preface>``, ``<intro>``, ``<content>`` ...)
    as a plain ``<div>``, with a small caption where ``_CONTAINER_LABELS``
    gives one."""
    eid = el.get("eId", "")
    label = _CONTAINER_LABELS.get(tag)
    header = f'<div class="akn-container-label">{label}</div>' if label else ""
    inner = "".join(_render_block(child) for child in el)
    id_attr = f' id="{html.escape(eid)}"' if eid else ""
    return (f'<div{id_attr} class="akn akn-{tag}" data-eid="{html.escape(eid)}">'
            f'{header}{inner}</div>')


def _render_structural(el: etree._Element, tag: str) -> str:
    """Render a provision: its label line, then everything beneath it.

    ``<num>`` and ``<heading>`` are joined into one label (``7. Transfer by
    counselling``), which is also what a click in split view uses to find the
    element in the XML pane. An ``hcontainer`` has no number of its own, so
    its ``name`` (``explanation``, ``schedule``) stands in for one.
    """
    eid = el.get("eId", "")
    num_el = el.find(_q("num"))
    heading_el = el.find(_q("heading"))
    subheading_el = el.find(_q("subheading"))

    label_bits = []
    if num_el is not None and (num_el.text or "").strip():
        label_bits.append(f'<span class="akn-num">{html.escape(num_el.text)}</span>')
    if heading_el is not None and (heading_el.text or "").strip():
        label_bits.append(
            f'<span class="akn-heading-text">{html.escape(heading_el.text)}</span>'
        )
    if tag == "hcontainer" and el.get("name"):
        label_bits.append(f'<span class="akn-name">[{html.escape(el.get("name"))}]</span>')
    label_html = f'<div class="akn-label">{" ".join(label_bits)}</div>' if label_bits else ""

    subheading_html = ""
    if subheading_el is not None:
        subheading_html = f'<div class="akn-subheading">{_inline_html(subheading_el)}</div>'

    body_html = "".join(
        _render_block(child) for child in el if _local(child.tag) not in _LABEL_TAGS
    )
    return (f'<div id="{html.escape(eid)}" class="akn akn-{tag}" '
            f'data-eid="{html.escape(eid)}" data-kind="{tag}">'
            f'{label_html}{subheading_html}{body_html}</div>')


def _render_p(el: etree._Element) -> str:
    eid = el.get("eId", "")
    return (f'<p id="{html.escape(eid)}" class="akn-p" data-eid="{html.escape(eid)}">'
            f'{_inline_html(el)}</p>')


def _render_table(el: etree._Element) -> str:
    """Render ``<table>`` as an HTML table, keeping ``<th>`` and ``<td>`` as found.

    The renderer already marks the first row as headers (see
    docs/akn-mapping.md#tables), so nothing is re-derived here. Each cell
    holds block content, usually a single ``<p>``.
    """
    eid = el.get("eId", "")
    rows = []
    for tr in el:
        if _local(tr.tag) != "tr":
            continue
        cells = []
        for cell in tr:
            ctag = _local(cell.tag)
            if ctag not in ("th", "td"):
                continue
            inner = "".join(_render_block(child) for child in cell)
            cells.append(f"<{ctag}>{inner}</{ctag}>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (f'<table id="{html.escape(eid)}" class="akn-table" '
            f'data-eid="{html.escape(eid)}"><tbody>{"".join(rows)}</tbody></table>')


def _inline_html(el: etree._Element) -> str:
    """Render mixed text/element content in document order.

    lxml keeps inline text as ``.text`` (before the first child) and
    ``.tail`` (after each child) rather than as sibling nodes, so this walks
    both explicitly instead of iterating children alone.
    """
    parts = [html.escape(el.text or "")]
    for child in el:
        parts.append(_render_inline(child))
        parts.append(html.escape(child.tail or ""))
    return "".join(parts)


def _render_inline(el: etree._Element) -> str:
    """Render one inline element: ``<ref>``, ``<def>``, ``<span>`` or ``<omissis>``."""
    tag = _local(el.tag)
    if tag == "ref":
        return _render_ref(el)
    if tag == "def":
        refers_to = el.get("refersTo", "")
        term_id = refers_to[1:] if refers_to.startswith("#") else refers_to
        title = f'Defined term: {html.escape(term_id)}' if term_id else "Defined term"
        return f'<dfn class="akn-def" title="{title}">{_inline_html(el)}</dfn>'
    if tag == "span":
        return _render_foreign(el)
    if tag == "omissis":
        return '<span class="akn-omissis" title="Text omitted under --foreign mark">[omitted]</span>'
    # An inline element this viewer does not specifically style: keep its
    # text so nothing is lost, just without special markup.
    return _inline_html(el)


def is_legacy_encoding(lang: str) -> bool:
    """Whether an ``xml:lang`` tag marks text as not yet usable Unicode.

    ``kn-Latn-x-*`` (a private-use subtag naming a legacy font encoding) and
    ``kn-x-misencoded`` both mean the codepoints are not the script they claim
    to be; see docs/languages.md#the-tags. Shared between the document
    renderer and the metadata pane so every place this text can surface in
    the viewer explains it the same way.
    """
    lower = lang.lower()
    return "-latn-" in lower or "misencoded" in lower


def _render_foreign(el: etree._Element) -> str:
    """Style a run of other-language text by what its ``xml:lang`` tag says.

    ``kn`` is text already in clean Kannada Unicode; it renders correctly and
    is only shaded to mark it as "not the requested language". A legacy
    encoding (see :func:`is_legacy_encoding`) means the bytes are not usable
    Unicode and look wrong on screen for that reason, not because the viewer
    failed to render them. The two need different explanations, so they get
    different styling rather than one generic "foreign text" look.
    """
    lang = el.get(XML_LANG, "")
    unconverted = is_legacy_encoding(lang)
    css_class = "akn-foreign akn-foreign-legacy" if unconverted else "akn-foreign"
    note = (
        "\nLegacy font encoding, not yet converted to Unicode. See docs/languages.md."
        if unconverted else ""
    )
    return (f'<span class="{css_class}" lang="{html.escape(lang)}" '
            f'title="xml:lang={html.escape(lang)}{note}">{_inline_html(el)}</span>')


def _render_ref(el: etree._Element) -> str:
    """Render a citation as a same-page link when its target is in this document."""
    href = el.get("href", "")
    text = _inline_html(el)
    if href.startswith("#"):
        return f'<a class="akn-ref" href="{html.escape(href)}">{text}</a>'
    # A citation into another component (a schedule referring back to the
    # main body) or an external instrument: not reachable by an in-page
    # anchor, so it is marked rather than made to look clickable-but-dead.
    return f'<span class="akn-ref akn-ref-external" title="{html.escape(href)}">{text}</span>'


# -- the collapsible outline -------------------------------------------

@dataclass
class OutlineNode:
    """One entry in the Outline tab: a provision, or a whole schedule.

    ``label`` is the number and heading as the reader sees them
    (``147. Payment of property tax``), falling back to the element name for
    a provision that has neither.
    """
    eid: str
    tag: str
    label: str
    children: list = field(default_factory=list)


def build_outline(root: etree._Element) -> list[OutlineNode]:
    """The document's hierarchy of provisions, for the collapsible tree pane."""
    act = root.find(_q("act"))
    if act is None:
        return []

    nodes = []
    body = act.find(_q("body"))
    if body is not None:
        nodes.extend(_outline_node(child) for child in body if _local(child.tag) in STRUCTURAL_TAGS)

    attachments = act.find(_q("attachments"))
    if attachments is not None:
        for index, attachment in enumerate(attachments, 1):
            doc = attachment.find(_q("doc"))
            main_body = doc.find(_q("mainBody")) if doc is not None else None
            children = (
                [_outline_node(child) for child in main_body
                 if _local(child.tag) in STRUCTURAL_TAGS]
                if main_body is not None else []
            )
            nodes.append(OutlineNode(
                eid=attachment.get("eId", ""), tag="attachment",
                label=f"Schedule {index}", children=children,
            ))
    return nodes


def _outline_node(el: etree._Element) -> OutlineNode:
    """Build the outline entry for *el* and, recursively, its child provisions.

    Only direct children are searched. Child provisions sit directly under
    their parent, never inside its ``<intro>`` or ``<content>`` (see
    docs/akn-mapping.md#content-model-content-versus-intro), so nothing is
    missed.
    """
    tag = _local(el.tag)
    num_el = el.find(_q("num"))
    heading_el = el.find(_q("heading"))
    label = " ".join(filter(None, [
        (num_el.text or "").strip() if num_el is not None else "",
        (heading_el.text or "").strip() if heading_el is not None else "",
    ])) or tag
    children = [
        _outline_node(child) for child in el if _local(child.tag) in STRUCTURAL_TAGS
    ]
    return OutlineNode(eid=el.get("eId", ""), tag=tag, label=label, children=children)


# -- metadata ------------------------------------------------------------

def extract_metadata(root: etree._Element) -> dict:
    """FRBR identity and gazette provenance, for the metadata pane."""
    ident = root.find(f"{_q('act')}/{_q('meta')}/{_q('identification')}")
    work = ident.find(_q("FRBRWork")) if ident is not None else None
    expr = ident.find(_q("FRBRExpression")) if ident is not None else None
    manif = ident.find(_q("FRBRManifestation")) if ident is not None else None
    pub = root.find(f"{_q('act')}/{_q('meta')}/{_q('publication')}")
    classification = root.find(f"{_q('act')}/{_q('meta')}/{_q('classification')}")

    def attr(el, tag, key):
        found = el.find(_q(tag)) if el is not None else None
        return found.get(key) if found is not None else None

    title, source_title, source_title_lang = None, None, None
    if work is not None:
        for alias in work.findall(_q("FRBRalias")):
            if alias.get("name") != "title":
                continue
            if alias.get(XML_LANG):
                source_title = alias.get("value")
                source_title_lang = alias.get(XML_LANG)
            else:
                title = alias.get("value")

    keywords = (
        [kw.get("showAs") for kw in classification.findall(_q("keyword"))]
        if classification is not None else []
    )

    return {
        "title": title,
        "source_title": source_title,
        "source_title_lang": source_title_lang,
        "source_title_legacy": bool(source_title_lang) and is_legacy_encoding(source_title_lang),
        "work_uri": attr(work, "FRBRuri", "value"),
        "expression_uri": attr(expr, "FRBRuri", "value"),
        "manifestation_uri": attr(manif, "FRBRuri", "value"),
        "jurisdiction": attr(work, "FRBRcountry", "value"),
        "number": attr(work, "FRBRnumber", "value"),
        "assent_date": attr(work, "FRBRdate", "date"),
        "publication_date": attr(expr, "FRBRdate", "date"),
        "generation_date": attr(manif, "FRBRdate", "date"),
        "language": attr(expr, "FRBRlanguage", "language"),
        "gazette": pub.get("name") if pub is not None else None,
        "notification": pub.get("number") if pub is not None else None,
        "keywords": keywords,
    }


# -- validation ------------------------------------------------------------

@lru_cache(maxsize=4)
def _validator(schema_path: str) -> Validator:
    """A ``Validator`` per schema path, built once and reused.

    Constructing one parses and compiles the Akoma Ntoso XSD, which costs
    more than everything else a page view does put together. The schema is
    immutable for the life of the process, so the viewer would otherwise pay
    that price again on every request.
    """
    return Validator(schema_path)


def validate(root: etree._Element, schema_path: str, target_lang: str):
    """Run the same checks the CLI report shows, against an already-written file.

    There is no ``CitationResolver`` for a file loaded back from disk, so
    ``unresolved_citations`` is always empty here: that count only exists
    while a PDF is being converted. Everything schema- and eId-derived is
    unaffected, since it is read from the XML itself.
    """
    return _validator(schema_path).check(root, target_lang)
