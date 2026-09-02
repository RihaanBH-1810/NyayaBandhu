"""
Document tree -> Akoma Ntoso 3.0 XML.

Two content-model rules from the OASIS schema drive most of this module, and
both were violated by the previous parser:

* a hierarchical element contains *either* ``<content>`` *or* the sequence
  ``intro?, (hierarchy|crossHeading)*, wrapUp?`` -- never a ``<content>``
  followed by child provisions.  Text that introduces sub-provisions therefore
  goes in ``<intro>``, and only leaf provisions get ``<content>``.
* ``<meta>`` has a fixed child order: identification, publication,
  classification, lifecycle, ..., references.

Provisos become the real ``<proviso>`` hierarchical element rather than
``<block name="proviso">``, and schedules become an ``<attachment>`` holding a
``<doc name="schedule">``, which is where AKN 3.0 puts end matter.
"""
from __future__ import annotations

import re

from lxml import etree

from . import transliterate
from .refs import CitationResolver
from .structure import TableBlock

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_LANG = f"{{{XML_NS}}}lang"
NSMAP = {None: AKN_NS}

_DEFINITION = re.compile(
    r'^\s*[""\']?(?P<term>[^""\'\n]{2,80}?)[""\']?\s*(?=\b(?:means|includes|shall mean)\b)'
)
_DEFINITION_SECTION = re.compile(r"\bdefinitions?\b", re.I)


def _q(tag: str) -> str:
    return f"{{{AKN_NS}}}{tag}"


class AknRenderer:
    def __init__(self, meta, resolver: CitationResolver):
        self.meta = meta
        self.refs = resolver
        self.terms: dict = {}
        self.foreign_runs: list = []
        self._in_attachment = False

    def _href(self, href: str) -> str:
        """Qualify a fragment reference made from inside an attachment.

        A bare ``#sec_2`` addresses the *current* component.  A schedule is a
        separate component, so a citation of the Act's sections from inside it
        has to name the component it means.
        """
        if self._in_attachment and href.startswith("#"):
            return self.meta.component_uri("expression", "main") + href
        return href

    # -- entry point -------------------------------------------------

    def render(self, document) -> etree._Element:
        root = etree.Element(_q("akomaNtoso"), nsmap=NSMAP)
        act = etree.SubElement(root, _q("act"))
        act.set("name", self.meta.doc_type)
        act.set("contains", "originalVersion")

        # The body is rendered first so that every defined term is known by
        # the time <references> is written.
        body_el = etree.Element(_q("body"))
        self._render_children(body_el, document.body)

        preface_el = self._preface(document)
        preamble_el = self._preamble(document)
        conclusions_el = self._conclusions(document)
        attachments_el = self._attachments(document)

        self._meta_block(act)
        for el in (preface_el, preamble_el):
            if el is not None:
                act.append(el)
        act.append(body_el)
        if conclusions_el is not None:
            act.append(conclusions_el)
        if attachments_el is not None:
            act.append(attachments_el)
        return root

    # -- metadata ----------------------------------------------------

    def _meta_block(self, act) -> None:
        m = self.meta
        meta = etree.SubElement(act, _q("meta"))

        ident = etree.SubElement(meta, _q("identification"))
        ident.set("source", f"#{m.editor_id}")

        work = etree.SubElement(ident, _q("FRBRWork"))
        self._sub(work, "FRBRthis", value=m.component_uri("work", "main"))
        self._sub(work, "FRBRuri", value=m.work_uri)
        if m.title:
            self._sub(work, "FRBRalias", name="title", value=m.title)
        if m.source_title:
            # The Act's name in the language it was enacted in.  Carried as a
            # Work-level alias because it names the Work, not this Expression.
            text, lang, encoding, font_encoding = m.source_title
            text, encoding = transliterate.convert(
                text, lang, encoding, font_encoding
            )
            alias = self._sub(work, "FRBRalias", name="title", value=text)
            alias.set(XML_LANG, transliterate.bcp47(lang, encoding, font_encoding))
        self._sub(work, "FRBRdate", date=m.work_date, name="assent")
        self._sub(work, "FRBRauthor", href=f"#{m.author_id}")
        self._sub(work, "FRBRcountry", value=m.jurisdiction)
        self._sub(work, "FRBRnumber", value=m.number)

        expr = etree.SubElement(ident, _q("FRBRExpression"))
        self._sub(expr, "FRBRthis", value=m.component_uri("expression", "main"))
        self._sub(expr, "FRBRuri", value=m.expression_uri)
        self._sub(expr, "FRBRdate", date=m.expression_date, name="publication")
        self._sub(expr, "FRBRauthor", href=f"#{m.author_id}")
        self._sub(expr, "FRBRlanguage", language=m.language)

        manif = etree.SubElement(ident, _q("FRBRManifestation"))
        self._sub(manif, "FRBRthis", value=m.component_uri("manifestation", "main"))
        self._sub(manif, "FRBRuri", value=m.manifestation_uri)
        self._sub(manif, "FRBRdate", date=m.manifestation_date, name="generation")
        self._sub(manif, "FRBRauthor", href=f"#{m.editor_id}")
        self._sub(manif, "FRBRformat", value="xml")

        pub = etree.SubElement(meta, _q("publication"))
        pub.set("date", m.expression_date)
        pub.set("name", m.gazette)
        pub.set("showAs", m.gazette)
        if m.notification:
            pub.set("number", m.notification)

        if m.keywords:
            classification = etree.SubElement(meta, _q("classification"))
            classification.set("source", f"#{m.editor_id}")
            for value in m.keywords:
                kw = etree.SubElement(classification, _q("keyword"))
                kw.set("eId", _slug(value))
                kw.set("value", value.lower())
                kw.set("showAs", value)
                # 'dictionary' is required by the schema.
                kw.set("dictionary", "#nyayabandhuSubjects")

        lifecycle = etree.SubElement(meta, _q("lifecycle"))
        lifecycle.set("source", f"#{m.editor_id}")
        ev = etree.SubElement(lifecycle, _q("eventRef"))
        ev.set("eId", "eref_1")
        ev.set("date", m.work_date)
        # eventRef/@type is restricted to generation | amendment | repeal;
        # 'publication' (used by the previous parser) is not a legal value.
        ev.set("type", "generation")
        ev.set("source", f"#{m.author_id}")

        refs = etree.SubElement(meta, _q("references"))
        refs.set("source", f"#{m.editor_id}")
        org = etree.SubElement(refs, _q("TLCOrganization"))
        org.set("eId", m.author_id)
        org.set("href", f"/akn/ontology/organization/{m.jurisdiction}/legislature")
        org.set("showAs", m.author_name)
        pubo = etree.SubElement(refs, _q("TLCOrganization"))
        pubo.set("eId", m.publisher_id)
        pubo.set("href", f"/akn/ontology/organization/{m.jurisdiction}/gazette")
        pubo.set("showAs", m.publisher_name)
        role = etree.SubElement(refs, _q("TLCRole"))
        role.set("eId", m.editor_id)
        role.set("href", "/akn/ontology/role/editor")
        role.set("showAs", m.editor_name)
        for eid, showAs in sorted(self.terms.items()):
            term = etree.SubElement(refs, _q("TLCTerm"))
            term.set("eId", eid)
            term.set("href", f"/akn/ontology/term/{eid}")
            term.set("showAs", showAs)

    @staticmethod
    def _sub(parent, tag: str, **attrs):
        el = etree.SubElement(parent, _q(tag))
        for key, value in attrs.items():
            if value:
                el.set(key, value)
        return el

    # -- front and back matter ---------------------------------------

    def _preface(self, document):
        if not document.preface and not document.long_title:
            return None
        preface = etree.Element(_q("preface"))
        preface.set("eId", "preface")
        for i, line in enumerate(document.preface, 1):
            self._paragraph(preface, line, f"preface__p_{i}", "")
        if document.long_title:
            lt = etree.SubElement(preface, _q("longTitle"))
            lt.set("eId", "preface__longTitle_1")
            self._paragraph(lt, document.long_title, "preface__longTitle_1__p_1", "")
        return preface

    def _preamble(self, document):
        if not document.recitals and not document.enacting_formula:
            return None
        preamble = etree.Element(_q("preamble"))
        preamble.set("eId", "preamble")
        if document.recitals:
            recitals = etree.SubElement(preamble, _q("recitals"))
            recitals.set("eId", "preamble__recitals_1")
            for i, line in enumerate(document.recitals, 1):
                rec = etree.SubElement(recitals, _q("recital"))
                rec.set("eId", f"preamble__recitals_1__rec_{i}")
                self._paragraph(
                    rec, line, f"preamble__recitals_1__rec_{i}__p_1", ""
                )
        if document.enacting_formula:
            formula = etree.SubElement(preamble, _q("formula"))
            formula.set("eId", "preamble__formula_1")
            formula.set("name", "enactingFormula")
            self._paragraph(
                formula, document.enacting_formula, "preamble__formula_1__p_1", ""
            )
        return preamble

    def _conclusions(self, document):
        if not document.conclusions:
            return None
        concl = etree.Element(_q("conclusions"))
        concl.set("eId", "conclusions")
        for i, line in enumerate(document.conclusions, 1):
            self._paragraph(concl, line, f"conclusions__p_{i}", "")
        return concl

    def _attachments(self, document):
        if not document.schedules:
            return None
        attachments = etree.Element(_q("attachments"))
        self._in_attachment = True
        for index, schedule in enumerate(document.schedules, 1):
            att = etree.SubElement(attachments, _q("attachment"))
            att.set("eId", schedule.eid or f"att_{index}")
            doc = etree.SubElement(att, _q("doc"))
            doc.set("name", "schedule")
            self._component_meta(doc, f"schedule_{index}")

            main = etree.SubElement(doc, _q("mainBody"))
            main.set("eId", f"{att.get('eId')}__body")
            if schedule.container is not None:
                self._render_node(main, schedule.container)
        self._in_attachment = False
        return attachments

    def _component_meta(self, doc, component: str) -> None:
        m = self.meta
        meta = etree.SubElement(doc, _q("meta"))
        ident = etree.SubElement(meta, _q("identification"))
        ident.set("source", f"#{m.editor_id}")
        work = etree.SubElement(ident, _q("FRBRWork"))
        self._sub(work, "FRBRthis", value=m.component_uri("work", component))
        self._sub(work, "FRBRuri", value=m.work_uri)
        self._sub(work, "FRBRdate", date=m.work_date, name="assent")
        self._sub(work, "FRBRauthor", href=f"#{m.author_id}")
        self._sub(work, "FRBRcountry", value=m.jurisdiction)
        expr = etree.SubElement(ident, _q("FRBRExpression"))
        self._sub(expr, "FRBRthis", value=m.component_uri("expression", component))
        self._sub(expr, "FRBRuri", value=m.expression_uri)
        self._sub(expr, "FRBRdate", date=m.expression_date, name="publication")
        self._sub(expr, "FRBRauthor", href=f"#{m.author_id}")
        self._sub(expr, "FRBRlanguage", language=m.language)
        manif = etree.SubElement(ident, _q("FRBRManifestation"))
        self._sub(manif, "FRBRthis", value=m.component_uri("manifestation", component))
        self._sub(manif, "FRBRuri", value=m.manifestation_uri)
        self._sub(manif, "FRBRdate", date=m.manifestation_date, name="generation")
        self._sub(manif, "FRBRauthor", href=f"#{m.editor_id}")

    # -- body --------------------------------------------------------

    def _render_children(self, parent, nodes, in_definitions: bool = False) -> None:
        for node in nodes:
            self._render_node(parent, node, in_definitions)

    def _render_node(self, parent, node, in_definitions: bool = False) -> None:
        if node.kind == "crossHeading":
            ch = etree.SubElement(parent, _q("crossHeading"))
            ch.set("eId", node.eid)
            ch.text = node.heading
            return

        el = etree.SubElement(parent, _q(node.kind))
        el.set("eId", node.eid)
        if node.kind == "hcontainer":
            el.set("name", node.name or "container")

        if node.num:
            num = etree.SubElement(el, _q("num"))
            num.text = self._display_num(node)
        if node.heading:
            heading = etree.SubElement(el, _q("heading"))
            heading.text = node.heading
        if node.subheading:
            subheading = etree.SubElement(el, _q("subheading"))
            subheading.set("eId", f"{node.eid}__subheading")
            self._inline(subheading, node.subheading, node.eid)

        defines = in_definitions or (
            node.kind == "section" and _DEFINITION_SECTION.search(node.heading or "")
        )

        if node.children:
            if node.paragraphs:
                intro = etree.SubElement(el, _q("intro"))
                intro.set("eId", f"{node.eid}__intro")
                self._paragraphs(intro, node.paragraphs, node.eid, defines)
            self._render_children(el, node.children, defines)
            if node.wrap_paragraphs:
                wrap = etree.SubElement(el, _q("wrapUp"))
                wrap.set("eId", f"{node.eid}__wrapup")
                self._paragraphs(wrap, node.wrap_paragraphs, node.eid, defines)
        else:
            paragraphs = node.paragraphs + node.wrap_paragraphs
            if paragraphs:
                content = etree.SubElement(el, _q("content"))
                content.set("eId", f"{node.eid}__content")
                self._paragraphs(content, paragraphs, node.eid, defines)

    def _paragraphs(self, parent, blocks, context_eid: str, defines: bool) -> None:
        index = 0
        for block in blocks:
            if isinstance(block, TableBlock):
                self._table(parent, block, context_eid)
                continue
            index += 1
            self._paragraph(
                parent, block, f"{parent.get('eId')}__p_{index}", context_eid, defines
            )

    def _display_num(self, node) -> str:
        if node.kind in ("section", "article", "rule"):
            return f"{node.num}."
        if node.kind in ("chapter", "part"):
            return node.num
        return f"({node.num})"

    # -- inline ------------------------------------------------------

    def _paragraph(self, parent, text: str, eid: str, context_eid: str,
                   defines: bool = False):
        p = etree.SubElement(parent, _q("p"))
        p.set("eId", eid)
        if defines:
            text = self._emit_definition(p, text)
            if text is None:
                return p
        self._inline(p, text, context_eid)
        return p

    def _emit_definition(self, p, text: str):
        """Wrap the defined term of a definition clause in ``<def>``.

        Returns the remaining text, or ``None`` if nothing was wrapped.
        """
        m = _DEFINITION.match(text)
        if not m:
            return text
        term = m.group("term").strip().strip('"“”\'')
        if not term or len(term) > 80:
            return text
        eid = _slug(term)
        self.terms[eid] = term
        d = etree.SubElement(p, _q("def"))
        d.set("eId", f"{p.get('eId')}__def_1")
        d.set("refersTo", f"#{eid}")
        matched = text[m.start():m.end()]
        d.text = matched.rstrip()
        self._inline_tail(p, d, matched[len(d.text):] + text[m.end():], "")
        return None

    def _inline(self, p, text: str, context_eid: str, after=None) -> None:
        """Emit marked-up text into *p*, continuing after element *after*."""
        last = after
        for seg in self.refs.markup(text, context_eid):
            if seg.kind == "text":
                if last is None:
                    p.text = (p.text or "") + seg.text
                else:
                    last.tail = (last.tail or "") + seg.text
            elif seg.kind == "ref":
                el = etree.SubElement(p, _q("ref"))
                el.set("eId", f"{p.get('eId')}__ref_{len(p)}")
                el.set("href", self._href(seg.href))
                el.text = seg.text
                last = el
            elif seg.kind == "omissis":
                el = etree.SubElement(p, _q("omissis"))
                el.set("eId", f"{p.get('eId')}__omissis_{len(p)}")
                last = el
            elif seg.kind == "foreign":
                last = self._foreign(p, seg)

    def _inline_tail(self, p, after, text: str, context_eid: str) -> None:
        self._inline(p, text, context_eid, after=after)

    def _foreign(self, p, seg):
        """Emit a run of text in another language, tagged for what it is.

        The text is preserved rather than dropped, and ``xml:lang`` records
        both the language and -- through a private-use subtag -- whether the
        codepoints have yet been converted out of a legacy font encoding.
        """
        text, encoding = transliterate.convert(
            seg.text, seg.lang, seg.encoding, seg.font_encoding
        )
        tag = transliterate.bcp47(seg.lang, encoding, seg.font_encoding)
        el = etree.SubElement(p, _q("span"))
        el.set("eId", f"{p.get('eId')}__span_{len(p)}")
        el.set(XML_LANG, tag)
        el.text = text
        self.foreign_runs.append((seg.lang, encoding, text))
        return el

    # -- tables ------------------------------------------------------

    def _table(self, parent, block, context_eid: str) -> None:
        table = etree.SubElement(parent, _q("table"))
        table.set("eId", block.eid)
        for r, row in enumerate(block.rows, 1):
            tr = etree.SubElement(table, _q("tr"))
            tr.set("eId", f"{block.eid}__tr_{r}")
            cell_tag = "th" if r == 1 else "td"
            for c, cell in enumerate(row, 1):
                td = etree.SubElement(tr, _q(cell_tag))
                td.set("eId", f"{block.eid}__tr_{r}__{cell_tag}_{c}")
                self._paragraph(td, cell, f"{td.get('eId')}__p_1", context_eid)


def _slug(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return "term"
    head, *rest = words
    return head.lower() + "".join(w.capitalize() for w in rest)


def serialise(root) -> bytes:
    etree.indent(root, space="  ")
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
