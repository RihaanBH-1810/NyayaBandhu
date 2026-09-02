"""
Checks run on every generated document.

Schema validation is done against the official OASIS Akoma Ntoso 3.0 XSD
(``schemas/akomantoso30.xsd``), which is the only authority on what is legal
AKN.  Three further checks catch problems the schema cannot see:

* **eId syntax** -- the schema accepts any string, but the naming convention
  does not.
* **Dangling references** -- ``<ref href="#sec_99">`` where ``sec_99`` does not
  exist is well-formed and schema-valid, and completely wrong.
* **Language residue** -- characters of a script other than the target
  language surviving into the output means the redaction pass missed
  something.
"""
from __future__ import annotations

import dataclasses
import os

from lxml import etree

from . import language
from .eids import is_conformant
from .render import AKN_NS

_NS = {"akn": AKN_NS}

_XML_NS = "http://www.w3.org/XML/1998/namespace"

#: Internal language key -> the xml:lang prefix that means "this language".
_LANG_PREFIX = {"eng": "en", "kan": "kn"}

#: Elements that open their own eId namespace (AKN Naming Convention 5.4.1:
#: "all document classes are always contexts").
_DOCUMENT_TAGS = frozenset(
    f"{{{AKN_NS}}}{name}"
    for name in (
        "act", "bill", "doc", "judgment", "debate", "debateReport",
        "statement", "amendment", "amendmentList", "officialGazette",
        "documentCollection", "portion",
    )
)


@dataclasses.dataclass
class ValidationReport:
    schema_valid: bool | None = None
    schema_errors: list = dataclasses.field(default_factory=list)
    duplicate_eids: list = dataclasses.field(default_factory=list)
    malformed_eids: list = dataclasses.field(default_factory=list)
    dangling_refs: list = dataclasses.field(default_factory=list)
    foreign_residue: dict = dataclasses.field(default_factory=dict)
    tagged_runs: int = 0
    unresolved_citations: list = dataclasses.field(default_factory=list)
    counts: dict = dataclasses.field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return (
            self.schema_valid is not False
            and not self.duplicate_eids
            and not self.malformed_eids
            and not self.dangling_refs
            and not self.foreign_residue
        )

    def summary(self) -> str:
        lines = []
        schema = {True: "valid", False: "INVALID", None: "not checked"}[self.schema_valid]
        lines.append(f"    AKN 3.0 schema : {schema}")
        for err in self.schema_errors[:10]:
            lines.append(f"        line {err[0]}: {err[1]}")
        if len(self.schema_errors) > 10:
            lines.append(f"        ... and {len(self.schema_errors) - 10} more")
        lines.append(
            f"    eIds           : {self.counts.get('eids', 0)} "
            f"({len(self.duplicate_eids)} duplicate, "
            f"{len(self.malformed_eids)} malformed)"
        )
        lines.append(
            f"    references     : {self.counts.get('refs', 0)} internal, "
            f"{self.counts.get('external', 0)} left external, "
            f"{len(self.dangling_refs)} dangling"
        )
        if self.unresolved_citations:
            lines.append(
                f"    unresolved     : {len(self.unresolved_citations)} citation(s)"
            )
            for w in self.unresolved_citations[:5]:
                lines.append(f"        {w.context or '(top level)'}: "
                             f"{w.citation!r} -- {w.reason}")
        if self.tagged_runs:
            lines.append(
                f"    other language : {self.tagged_runs} run(s) kept and tagged"
            )
        if self.foreign_residue:
            lines.append(f"    UNTAGGED script: {self.foreign_residue}")
        return "\n".join(lines)


class Validator:
    def __init__(self, schema_path: str = ""):
        self.schema = None
        self.schema_path = schema_path
        if schema_path and os.path.exists(schema_path):
            self.schema = etree.XMLSchema(etree.parse(schema_path))

    def check(self, root, target_lang: str, resolver=None) -> ValidationReport:
        report = ValidationReport()

        if self.schema is not None:
            tree = etree.ElementTree(root)
            report.schema_valid = bool(self.schema.validate(tree))
            report.schema_errors = [
                (e.line, e.message) for e in self.schema.error_log
            ]

        seen = set()
        for el in root.iter():
            eid = el.get("eId")
            if eid is None:
                continue
            if eid in seen:
                report.duplicate_eids.append(eid)
            seen.add(eid)
            if not is_conformant(eid):
                report.malformed_eids.append(eid)
        report.counts["eids"] = len(seen)

        refs = root.findall(f".//{{{AKN_NS}}}ref")
        report.counts["refs"] = len(refs)
        for ref in refs:
            href = ref.get("href", "")
            # A bare fragment addresses this document; a URI with a fragment
            # addresses a component of it, and only the fragment is checkable
            # here.
            fragment = href.split("#", 1)[1] if "#" in href else ""
            if fragment and fragment not in seen:
                report.dangling_refs.append((href, ref.text))

        # Text inside an element tagged with a different xml:lang is there on
        # purpose; only untagged other-script text counts as residue.
        report.foreign_residue = self._residue(root, target_lang)
        report.tagged_runs = len(root.findall(f".//*[@{{{_XML_NS}}}lang]"))

        if resolver is not None:
            report.unresolved_citations = list(resolver.warnings)
            report.counts["external"] = resolver.external

        return report

    @staticmethod
    def _residue(root, target_lang: str) -> dict:
        counts = {}
        for el in root.iter():
            tagged = el.get(f"{{{_XML_NS}}}lang")
            if tagged and not tagged.startswith(_LANG_PREFIX.get(target_lang, "")):
                continue          # deliberately in another language
            for script, n in language.script_letter_counts(el.text or "").items():
                if script != target_lang and n:
                    counts[script] = counts.get(script, 0) + n
            for script, n in language.script_letter_counts(el.tail or "").items():
                if script != target_lang and n:
                    counts[script] = counts.get(script, 0) + n
        return counts

    @staticmethod
    def _scope_of(el):
        """The document element that owns *el*'s identifier namespace."""
        node = el
        while node is not None:
            if node.tag in _DOCUMENT_TAGS:
                return node
            node = node.getparent()
        return None
