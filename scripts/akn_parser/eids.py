"""
eId generation per the OASIS *Akoma Ntoso Naming Convention v1.0*, section 5.4.

Rules implemented here:

* an eId is ``<ancestor eId>__<element_ref>_<number>``.  Levels are separated
  by a **double** underscore, the element abbreviation from its number by a
  single one.  (The previous parser used ``-`` for both, which is not a legal
  AKN identifier, and used ``__`` as a de-duplication suffix -- colliding with
  the level separator.)
* ``element_ref`` is the element name, except for the abbreviations fixed by
  the specification (``section`` -> ``sec``, ``clause`` -> ``cl`` and so on).
* the ``number`` part is the content of ``<num>`` with leading/trailing
  punctuation stripped and internal separators reduced to ``-``.
* elements with no ``<num>`` (a proviso, for example) are counted locally
  within their parent.
* a ``doc`` starts a new numbering context, so identifiers inside an
  attachment restart.

Uniqueness is a *consequence* of these rules rather than something patched
afterwards: if two eIds collide it means the tree is wrong, so a collision is
raised rather than silently renamed.
"""
from __future__ import annotations

import re

#: Element name -> element_ref, for the elements this parser emits.
#: Anything absent uses its full element name, as the specification requires.
ELEMENT_REF = {
    "alinea": "al",
    "article": "art",
    "attachment": "att",
    "blockList": "list",
    "chapter": "chp",
    "clause": "cl",
    "component": "cmp",
    "components": "cmpnts",
    "division": "dvs",
    "mainBody": "body",
    "paragraph": "para",
    "section": "sec",
    "subchapter": "subchp",
    "subclause": "subcl",
    "subdivision": "subdvs",
    "subparagraph": "subpara",
    "subsection": "subsec",
    "wrapUp": "wrapup",
}

#: An eId as the naming convention defines it.
EID_SYNTAX = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9\-]+)?"
                        r"(?:__[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9\-]+)?)*$")


class DuplicateEId(ValueError):
    """Raised when two elements would be given the same eId."""


def element_ref(kind: str) -> str:
    return ELEMENT_REF.get(kind, kind)


def normalise_num(raw: str) -> str:
    """Reduce the text of a ``<num>`` to its identifier form.

    ``"(1)"`` -> ``1``; ``"12A."`` -> ``12A``; ``"Art. 11.2 bis"`` -> ``11-2bis``.
    Case is preserved, as the specification requires.
    """
    text = (raw or "").strip()
    text = re.sub(r"^(?:section|sec\.?|article|art\.?|clause|cl\.?|para\.?|"
                  r"paragraph|rule|item)\s+", "", text, flags=re.I)
    text = text.strip("()[]{}.,;:  \t")
    # Keep meaningful leading signs such as the "-1" of a late insertion.
    sign = "-" if text.startswith("-") else ""
    text = text.lstrip("-")
    # Whitespace is a "meaningless separation" and disappears; punctuation is
    # a meaningful one and becomes a hyphen.  Hence "Art. 11.2 bis" -> 11-2bis.
    text = re.sub(r"\s+", "", text)
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", text) if p]
    return sign + "-".join(parts)


class EIdAssigner:
    """Walk a document tree and stamp conformant eIds onto it."""

    def __init__(self):
        self.assigned: dict = {}

    def assign(self, document) -> dict:
        """Assign eIds to *document* and return the {eId: node} index.

        A schedule sits in a ``doc`` inside an ``attachment``, which the naming
        convention treats as a fresh numbering context.  Restarting the
        *counters* there is therefore correct, but the identifiers still carry
        the attachment's eId as their prefix -- the convention's own example is
        ``doc_1__body`` "in case of a composite document" -- and that also
        satisfies the schema, whose uniqueness constraint on ``act`` selects
        every descendant, attachments included.
        """
        self.assigned = {}
        counters: dict = {}
        for node in document.body:
            self._assign(node, "", counters)
        for index, schedule in enumerate(document.schedules, 1):
            schedule.eid = self._register(f"att_{index}", schedule)
            if schedule.container is not None:
                self._assign(schedule.container, schedule.eid, {})
        return self.assigned

    # -- internals ---------------------------------------------------

    def _assign(self, node, prefix: str, counters: dict) -> None:
        local = self._local(node, counters, element_ref(node.kind))
        node.eid = self._register(f"{prefix}__{local}" if prefix else local, node)

        # Tables are blocks inside this node's <content>/<intro>, so they are
        # numbered within it rather than as sibling provisions.
        for index, table in enumerate(node.tables(), 1):
            table.eid = self._register(f"{node.eid}__table_{index}", table)

        child_counters: dict = {}
        for child in node.children:
            self._assign(child, node.eid, child_counters)

    @staticmethod
    def _local(node, counters: dict, ref: str) -> str:
        number = normalise_num(getattr(node, "num", ""))
        if not number:
            counters[ref] = counters.get(ref, 0) + 1
            number = str(counters[ref])
        return f"{ref}_{number}"

    def _register(self, eid: str, node) -> str:
        if eid in self.assigned:
            raise DuplicateEId(
                f"eId {eid!r} generated twice "
                f"(for <{getattr(self.assigned[eid], 'kind', 'table')}> and "
                f"<{getattr(node, 'kind', 'table')}>). "
                f"This means the parsed hierarchy is wrong, not that the "
                f"identifier needs a suffix."
            )
        self.assigned[eid] = node
        return eid


def is_conformant(eid: str) -> bool:
    return bool(EID_SYNTAX.match(eid))
