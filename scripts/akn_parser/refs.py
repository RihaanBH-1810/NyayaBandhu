"""
Cross-reference detection and resolution.

The previous implementation looked for the literal string ``section N``, then
guessed whether the citation was external by searching a 200-character window
for the name of one of a hard-coded list of statutes.  That produced two
classes of wrong ``<ref>``: citations of other Acts linked to this Act's own
sections, and ``href`` values pointing at eIds that do not exist.

This module instead:

* parses a whole citation *chain* -- ``clause (i) to (iv) of sub-section (1)
  of section 10`` is one citation, not three;
* decides external/internal structurally, from the instrument named around
  the citation -- after it (``section 6 of the Karnataka General Clauses Act,
  1899``) or before it, as amending Acts write it (``In the ... Act, 2020
  (Karnataka Act 04 of 2020), in section 10``) -- so no list of statute names
  has to be maintained;
* resolves relative citations (``sub-section (3)`` inside section 18) against
  the element the text actually sits in; and
* emits a ``<ref>`` **only** when the target eId exists in the document.
  Anything else is left as plain text and reported.
"""
from __future__ import annotations

import dataclasses
import re

from .extract import FOREIGN_MARK_TOKEN, REDACTION_MARK, decode_foreign

#: Words that introduce a reference to a numbered provision.
_KEYWORD = (
    r"(?:sub[-\s]?sections?|sub[-\s]?clauses?|sub[-\s]?paragraphs?|sub[-\s]?rules?"
    r"|sections?|clauses?|paragraphs?|articles?|rules?|items?|chapters?|parts?"
    r"|categor(?:y|ies))"
)

#: Keyword -> the element_ref values that may satisfy it, in preference order.
#: Indian drafting is not consistent about "clause" versus "sub-clause" for the
#: same list (compare section 5(ii) with section 10(2) of the Teachers Transfer
#: Act), so both spellings accept both element_refs.
_KEYWORD_TARGETS = {
    "section": ("sec",),
    "subsection": ("subsec",),
    "clause": ("cl", "subcl", "point"),
    "subclause": ("subcl", "cl"),
    "paragraph": ("para", "subpara"),
    "subparagraph": ("subpara", "para"),
    "article": ("art",),
    "rule": ("rule",),
    "subrule": ("subrule",),
    "item": ("item", "cl"),
    "chapter": ("chp",),
    "part": ("part",),
    "category": ("cl", "subcl"),
}

_NUM_TOKEN = r"(?:\(\s*[0-9A-Za-z]{1,4}\s*\)|[0-9]{1,3}[A-Z]{0,2})"
_SEP = r"(?:\s*,\s*|\s+and\s+|\s+to\s+|\s*&\s*|\s+or\s+)"
_NUM_LIST = rf"{_NUM_TOKEN}(?:{_SEP}{_NUM_TOKEN})*"

CITATION_CHAIN = re.compile(
    rf"\b(?P<chain>{_KEYWORD}\s+{_NUM_LIST}"
    rf"(?:\s+of\s+(?:the\s+)?{_KEYWORD}\s+{_NUM_LIST})*)",
    re.I,
)

#: What makes a citation point outside this Act: it is followed by the name of
#: another instrument.  "of this Act" and "of the said Act" are excluded --
#: they are self-references and their sections do resolve internally.
EXTERNAL_TAIL = re.compile(
    r"^\s*(?:,\s*\d{4})?\s*of\s+(?!this\b|the\s+said\b|the\s+present\b)"
    r"(?:the\s+)?[^.;:]{0,90}?"
    r"\b(?:Act|Code|Rules?|Regulations?|Ordinance|Constitution|Order|Notification)\b",
    re.I,
)

#: The other way an external citation is written, with the instrument named
#: *before* the provision rather than after it.  Amending Acts always use this
#: form: "In the Karnataka ... Act, 2020 (Karnataka Act 04 of 2020), in
#: section 10, after sub-section (5), ...".  The instrument has to sit
#: immediately before the citation, so that a statute mentioned earlier in a
#: long sentence does not capture the Act's references to itself.
EXTERNAL_LEAD = re.compile(
    r"\b(?:Act|Code|Rules?|Regulations?|Ordinance)\b,?\s*\d{4}\s*"
    r"(?:\([^)]{0,80}\))?\s*[,;]?\s*(?:in|of|under)?\s*$",
    re.I,
)

#: "the fourth proviso"
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
ORDINAL_PROVISO = re.compile(
    rf"\b(?P<text>(?:the\s+)?({'|'.join(_ORDINALS)})\s+proviso)\b", re.I
)

#: "the Schedule" / "the First Schedule"
SCHEDULE_REF = re.compile(
    r"\b(?P<text>the\s+(?:First|Second|Third|Fourth|Fifth)?\s*Schedule)\b"
)

_SEP_SPLIT = re.compile(_SEP)
_NUM_FIND = re.compile(_NUM_TOKEN)
_KEYWORD_ONLY = re.compile(_KEYWORD, re.I)


@dataclasses.dataclass
class Segment:
    """One piece of a marked-up paragraph."""
    kind: str            # "text" | "ref" | "omissis" | "foreign"
    text: str = ""
    href: str = ""
    lang: str = ""       # foreign only: internal language key
    encoding: str = ""   # foreign only: unicode | legacy | suspect
    font_encoding: str = ""


@dataclasses.dataclass
class RefWarning:
    context: str
    citation: str
    reason: str


def _canonical_keyword(word: str) -> str:
    w = re.sub(r"[-\s]", "", word.lower())
    if w.endswith("ies"):
        w = w[:-3] + "y"
    elif w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def _num_key(token: str) -> str:
    return token.strip("() \t").lower()


class CitationResolver:
    """Turn plain paragraph text into a list of :class:`Segment`."""

    def __init__(self, eid_index: dict, schedule_eids: list = ()):
        self.eids = set(eid_index)
        self.schedule_eids = list(schedule_eids)
        self.warnings: list = []
        self._warned: set = set()
        self.internal = 0
        self.external = 0

        # eId -> its trailing component, for the outward search.
        self._by_tail: dict = {}
        for eid in self.eids:
            self._by_tail.setdefault(eid.rsplit("__", 1)[-1], []).append(eid)

    # -- public API --------------------------------------------------

    def markup(self, text: str, context_eid: str = "") -> list:
        segments = [Segment("text", text)]
        segments = self._apply(segments, CITATION_CHAIN, self._chain_segments, context_eid)
        segments = self._apply(segments, SCHEDULE_REF, self._schedule_segments, context_eid)
        segments = self._apply(
            segments, ORDINAL_PROVISO, self._proviso_segments, context_eid
        )
        return self._split_markers(segments)

    def _warn(self, context: str, citation: str, reason: str) -> None:
        """Record an unresolved citation once.

        One citation is examined at several depths -- as a whole chain and
        again as its innermost link -- so the same failure would otherwise be
        reported twice under different spellings ("sub-section (5)" and
        "subsection 5").
        """
        key = (context, re.sub(r"[^a-z0-9]", "", citation.lower()))
        if key in self._warned:
            return
        self._warned.add(key)
        self.warnings.append(RefWarning(context, citation, reason))

    # -- generic rewriting -------------------------------------------

    def _apply(self, segments: list, pattern, handler, context_eid: str) -> list:
        out = []
        for seg in segments:
            if seg.kind != "text":
                out.append(seg)
                continue
            pos = 0
            for m in pattern.finditer(seg.text):
                produced = handler(m, seg.text, context_eid)
                if produced is None:
                    continue
                if m.start() > pos:
                    out.append(Segment("text", seg.text[pos:m.start()]))
                out.extend(produced)
                pos = m.end()
            if pos < len(seg.text):
                out.append(Segment("text", seg.text[pos:]))
        return [s for s in out if s.kind != "text" or s.text]

    # -- handlers ----------------------------------------------------

    def _chain_segments(self, match, whole: str, context_eid: str):
        chain = match.group("chain")
        tail = whole[match.end():]
        lead = whole[: match.start()]

        if EXTERNAL_TAIL.match(tail) or EXTERNAL_LEAD.search(lead):
            self.external += 1
            return None  # leave the citation as plain text

        links = self._parse_chain(chain)
        if not links:
            return None

        base = self._resolve_outer(links, context_eid, chain)
        if base is None:
            return None

        head_keyword, head_numbers = links[0]
        targets = []
        for token in head_numbers:
            eid = self._resolve_child(base, head_keyword, token, context_eid)
            targets.append((token, eid))

        if len(targets) == 1 and targets[0][1]:
            self.internal += 1
            return [Segment("ref", chain, "#" + targets[0][1])]

        resolved = {tok: eid for tok, eid in targets if eid}
        if not resolved:
            self._warn(context_eid, chain, "no matching provision in this Act")
            return None
        return self._wrap_numbers(chain, resolved)

    def _wrap_numbers(self, chain: str, resolved: dict):
        out = []
        pos = 0
        for m in _NUM_FIND.finditer(chain):
            eid = resolved.get(_num_key(m.group()))
            if not eid:
                continue
            if m.start() > pos:
                out.append(Segment("text", chain[pos:m.start()]))
            out.append(Segment("ref", m.group(), "#" + eid))
            self.internal += 1
            pos = m.end()
        if pos < len(chain):
            out.append(Segment("text", chain[pos:]))
        return out

    def _schedule_segments(self, match, whole: str, context_eid: str):
        if not self.schedule_eids:
            return None
        return [Segment("ref", match.group("text"), "#" + self.schedule_eids[0])]

    def _proviso_segments(self, match, whole: str, context_eid: str):
        index = _ORDINALS[match.group(2).lower()]
        for ancestor in self._ancestors(context_eid):
            candidate = f"{ancestor}__proviso_{index}" if ancestor else f"proviso_{index}"
            if candidate in self.eids:
                self.internal += 1
                return [Segment("ref", match.group("text"), "#" + candidate)]
        self._warn(context_eid, match.group("text"), "no such proviso")
        return None

    # -- chain parsing and resolution --------------------------------

    @staticmethod
    def _parse_chain(chain: str):
        """``clause (i) to (iv) of sub-section (1) of section 10`` ->
        ``[("clause", ["i","iv"]), ("subsection", ["1"]), ("section", ["10"])]``
        """
        links = []
        for part in re.split(r"\s+of\s+(?:the\s+)?", chain):
            m = _KEYWORD_ONLY.match(part)
            if not m:
                return []
            keyword = _canonical_keyword(m.group())
            numbers = [_num_key(t) for t in _NUM_FIND.findall(part[m.end():])]
            if not numbers:
                return []
            links.append((keyword, numbers))
        return links

    def _resolve_outer(self, links, context_eid: str, chain: str):
        """Resolve everything except the innermost link, returning its eId.

        The empty string means "resolve the innermost link relative to the
        context", which is what a bare ``sub-section (3)`` needs.
        """
        if len(links) == 1:
            return ""

        keyword, numbers = links[-1]
        eid = self._absolute(keyword, numbers[0])
        if eid is None:
            # The outermost link can itself be relative: "clause (b) of
            # sub-section (2)" names no section, so the subsection is the one
            # in whatever provision the sentence sits in.
            eid = self._resolve_relative(keyword, numbers[0], context_eid)
        if eid is None:
            self._warn(context_eid, chain, f"no {keyword} {numbers[0]} in this Act")
            return None

        for keyword, numbers in reversed(links[1:-1]):
            child = self._child_of(eid, keyword, numbers[0])
            if child is None:
                self._warn(context_eid, chain,
                           f"{keyword} {numbers[0]} not found under {eid}")
                return None
            eid = child
        return eid

    def _absolute(self, keyword: str, number: str):
        """Find a provision cited by number alone, e.g. "section 208".

        In an Act with chapters the section is not at the top of the tree --
        section 208 of the BBMP Act has the eId ``chp_XV__sec_208`` -- so a
        top-level lookup alone finds nothing.  A match on the last component
        is accepted when it is unambiguous.
        """
        for ref in _KEYWORD_TARGETS.get(keyword, ()):
            candidate = f"{ref}_{number}"
            if candidate in self.eids:
                return candidate
            matches = self._by_tail.get(candidate, [])
            if len(matches) == 1:
                return matches[0]
        return None

    def _child_of(self, parent: str, keyword: str, number: str):
        for ref in _KEYWORD_TARGETS.get(keyword, ()):
            candidate = f"{parent}__{ref}_{number}" if parent else f"{ref}_{number}"
            if candidate in self.eids:
                return candidate
        return None

    def _resolve_child(self, base: str, keyword: str, number: str, context_eid: str):
        if base:
            return self._child_of(base, keyword, number)
        return self._resolve_relative(keyword, number, context_eid)

    def _resolve_relative(self, keyword: str, number: str, context_eid: str):
        """Find ``keyword number`` as seen from *context_eid*.

        Searches outwards: the context itself, then each ancestor, then any
        descendant of the enclosing section.  The last step is what makes
        section 10(2)'s "clauses (i) to (iv)" resolve to the clauses of
        section 10(1).
        """
        refs = _KEYWORD_TARGETS.get(keyword, ())
        for ancestor in self._ancestors(context_eid):
            found = self._child_of(ancestor, keyword, number)
            if found:
                return found

        # Absolute fallback for top-level units such as "section 7".
        found = self._absolute(keyword, number)
        if found:
            return found

        # Widen to anything under the enclosing section.
        section = context_eid.split("__", 1)[0] if context_eid else ""
        if section:
            for ref in refs:
                tail = f"{ref}_{number}"
                candidates = sorted(
                    eid for eid in self._by_tail.get(tail, [])
                    if eid.startswith(section + "__")
                )
                if candidates:
                    return candidates[0]

        self._warn(context_eid, f"{keyword} {number}",
                   "no matching provision in this Act")
        return None

    @staticmethod
    def _ancestors(eid: str):
        """The context eId and each of its ancestors, innermost first."""
        parts = eid.split("__") if eid else []
        for i in range(len(parts), 0, -1):
            yield "__".join(parts[:i])
        yield ""

    # -- other-language markers --------------------------------------

    _MARKER = re.compile(
        f"({REDACTION_MARK}|{FOREIGN_MARK_TOKEN}[A-Za-z0-9_=-]+{FOREIGN_MARK_TOKEN})"
    )

    @classmethod
    def _split_markers(cls, segments: list) -> list:
        """Turn redaction marks and other-language tokens into their own segments."""
        out = []
        for seg in segments:
            if seg.kind != "text" or not cls._MARKER.search(seg.text):
                out.append(seg)
                continue
            for part in cls._MARKER.split(seg.text):
                if not part:
                    continue
                if part == REDACTION_MARK:
                    out.append(Segment("omissis"))
                elif part.startswith(FOREIGN_MARK_TOKEN):
                    decoded = decode_foreign(part)
                    if decoded is None:
                        continue
                    text, lang, encoding, font_encoding = decoded
                    out.append(Segment("foreign", text, lang=lang,
                                       encoding=encoding,
                                       font_encoding=font_encoding))
                else:
                    out.append(Segment("text", part))
        return out
