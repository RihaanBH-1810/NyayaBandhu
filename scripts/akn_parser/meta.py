"""
FRBR metadata.

The previous version hard-coded the BBMP Act's identifiers into the parser, so
every document it produced claimed to be the BBMP Act.  Here the identifiers
are derived from the document's own front matter (act number, assent date,
first-publication date, title), with a per-document JSON file available to
override or supply anything the text does not carry.

URI shape follows the OASIS *Akoma Ntoso Naming Convention v1.0* section 4:

    Work           /akn/in-ka/act/2020-03-26/4
    Work component /akn/in-ka/act/2020-03-26/4/!main
    Expression     /akn/in-ka/act/2020-03-26/4/eng@2020-03-27
    Manifestation  /akn/in-ka/act/2020-03-26/4/eng@2020-03-27.xml

Note that the date in a Work URI is the *full* date the Work came into being
(here, assent), not just the year, and that components are introduced by
``/!``.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import re

from .extract import FOREIGN_MARK_TOKEN, decode_foreign

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], 1)
}

_RE_ACT_NUMBER = re.compile(
    r"\b(?P<state>[A-Z][A-Za-z]+)\s+ACT\s+NO\.?\s*(?P<number>[0-9]+[A-Z]?)\s+OF\s+(?P<year>\d{4})",
    re.I,
)
_RE_ASSENT = re.compile(
    r"assent of the (?:Governor|President)[^)]*?on the\s+(?P<day>\d{1,2})\w*\s+day of\s+"
    r"(?P<month>[A-Za-z]+),?\s*(?P<year>\d{4})",
    re.I,
)
_RE_PUBLISHED = re.compile(
    r"First Published in the (?P<gazette>[^)]*?Gazette[^)]*?)\s+on the\s+(?P<day>\d{1,2})\w*\s+"
    r"day of\s+(?P<month>[A-Za-z]+),?\s*(?P<year>\d{4})",
    re.I,
)
_RE_TITLE = re.compile(r"^THE\s+.+?ACT,\s*\d{4}\s*$")
_RE_NOTIFICATION = re.compile(r"No\.?\s*(?P<no>[A-Z]{2,6}\s+\d+\s+[A-Z]+\s+\d{4})")

#: The notification names the Act in the enacting language before saying that
#: a translation of it is being published: "Ordered that the translation of
#: <Kannada title> in the English language, be published ...".  That run is the
#: Act's own name, not incidental foreign text, so it is worth keeping as an
#: alias rather than leaving it only in the body.
_RE_SOURCE_TITLE = re.compile(
    r"translation\s+of\s*"
    f"({FOREIGN_MARK_TOKEN}[A-Za-z0-9_=-]+{FOREIGN_MARK_TOKEN})"
    r"\s*in\s+the\s+English\s+language",
    re.I,
)

#: Where the Act comes from.  ISO 3166-2 subdivision codes, lowercased, as the
#: naming convention requires.
JURISDICTIONS = {
    "karnataka": "in-ka",
    "kerala": "in-kl",
    "maharashtra": "in-mh",
    "tamil nadu": "in-tn",
    "india": "in",
}


@dataclasses.dataclass
class DocumentMeta:
    jurisdiction: str = "in-ka"
    doc_type: str = "act"
    number: str = "nn"
    year: str = ""
    work_date: str = ""            # date of the Work (assent)
    expression_date: str = ""      # date of this Expression (publication)
    manifestation_date: str = ""
    language: str = "eng"
    title: str = ""
    short_name: str = ""
    gazette: str = "Karnataka Gazette Extraordinary"
    notification: str = ""
    author_id: str = "karnatakaLegislature"
    author_name: str = "Karnataka State Legislature"
    publisher_id: str = "karnatakaGazette"
    publisher_name: str = "Karnataka Gazette"
    editor_id: str = "nyayabandhu"
    editor_name: str = "NyayaBandhu automated parser"
    keywords: list = dataclasses.field(default_factory=list)
    source_pdf: str = ""
    #: The Act's title in the language it was enacted in, as
    #: (text, language, encoding, legacy font encoding).
    source_title: tuple = ()

    # -- FRBR URIs ---------------------------------------------------

    @property
    def work_uri(self) -> str:
        date = self.work_date or self.year or "nn"
        return f"/akn/{self.jurisdiction}/{self.doc_type}/{date}/{self.number}"

    @property
    def expression_uri(self) -> str:
        at = f"@{self.expression_date}" if self.expression_date else "@"
        return f"{self.work_uri}/{self.language}{at}"

    @property
    def manifestation_uri(self) -> str:
        return f"{self.expression_uri}.xml"

    def component_uri(self, level: str, component: str) -> str:
        base = {
            "work": self.work_uri,
            "expression": self.expression_uri,
            "manifestation": self.expression_uri,
        }[level]
        suffix = ".xml" if level == "manifestation" else ""
        return f"{base}/!{component}{suffix}"


def _iso(day, month, year) -> str:
    index = _MONTHS.get(str(month).lower()[:3] and str(month).lower(), None)
    if index is None:
        for name, i in _MONTHS.items():
            if name.startswith(str(month).lower()[:3]):
                index = i
                break
    if index is None:
        return ""
    return dt.date(int(year), index, int(day)).isoformat()


class MetadataExtractor:
    """Read what the gazette itself states, then apply file overrides."""

    def __init__(self, overrides_path: str = ""):
        self.overrides = {}
        if overrides_path and os.path.exists(overrides_path):
            with open(overrides_path, encoding="utf-8") as fh:
                self.overrides = json.load(fh)

    def build(self, document, source_pdf: str, language: str) -> DocumentMeta:
        front = "\n".join(document.preface + [document.long_title])
        meta = DocumentMeta(language=language, source_pdf=os.path.basename(source_pdf))

        m = _RE_ACT_NUMBER.search(front)
        if m:
            meta.number = m.group("number").lstrip("0") or "0"
            meta.year = m.group("year")
            meta.jurisdiction = JURISDICTIONS.get(
                m.group("state").lower(), meta.jurisdiction
            )

        m = _RE_ASSENT.search(front)
        if m:
            meta.work_date = _iso(m.group("day"), m.group("month"), m.group("year"))

        m = _RE_PUBLISHED.search(front)
        if m:
            meta.expression_date = _iso(m.group("day"), m.group("month"), m.group("year"))
            meta.gazette = re.sub(r"\s+", " ", m.group("gazette")).strip()

        for line in document.preface:
            if _RE_TITLE.match(line.strip()):
                meta.title = re.sub(r"\s+", " ", line.strip())
                break
        if not meta.title and document.long_title:
            meta.title = document.long_title

        m = _RE_SOURCE_TITLE.search(front)
        if m:
            decoded = decode_foreign(m.group(1))
            if decoded:
                text, lang, encoding, font_encoding = decoded
                meta.source_title = (text.strip(), lang, encoding, font_encoding)

        m = _RE_NOTIFICATION.search(front)
        if m:
            meta.notification = re.sub(r"\s+", " ", m.group("no"))

        if not meta.work_date and meta.year:
            meta.work_date = meta.year
        if not meta.expression_date:
            meta.expression_date = meta.work_date
        meta.manifestation_date = dt.date.today().isoformat()
        meta.short_name = _short_name(meta.title)

        self._apply_overrides(meta)
        return meta

    def _apply_overrides(self, meta: DocumentMeta) -> None:
        for key in (meta.source_pdf, os.path.splitext(meta.source_pdf)[0]):
            values = self.overrides.get(key)
            if not values:
                continue
            for field, value in values.items():
                if hasattr(meta, field):
                    setattr(meta, field, value)


def _short_name(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title.title())
    return "".join(words) or "Act"
