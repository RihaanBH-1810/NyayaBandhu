"""
Logical lines -> a document tree.

Two things make Indian legislative numbering awkward to parse:

1. ``(i)`` is ambiguous.  In section 2 of the Teachers Transfer Act it is the
   ninth *alphabetic* clause (it follows ``(h)``); in section 10(1) it is the
   first *roman* clause.  The tokenizer therefore resolves ``(i)``, ``(v)`` and
   ``(x)`` by looking at the surrounding enumerators rather than in isolation.

2. Depth is positional, not lexical.  ``(i)`` under a subsection is one level
   down; ``(i)`` under a clause is two.  The tree builder assigns the Akoma
   Ntoso element name from the parent, so the same marker becomes ``clause`` or
   ``subclause`` according to where it actually sits.
"""
from __future__ import annotations

import dataclasses
import re

from .extract import TABLE_MARK, decode_table
from .normalize import ROMAN

# -- token kinds ------------------------------------------------------

T_CHAPTER = "chapter"
T_PART = "part"
T_SECTION = "section"
T_SUBSECTION = "subsection"
T_ALPHA = "alpha"
T_ROMAN = "roman"
T_PROVISO = "proviso"
T_EXPLANATION = "explanation"
T_SCHEDULE = "schedule"
T_TABLE = "table"
T_HEADING = "heading"
T_TEXT = "text"

_RE_CHAPTER = re.compile(r"^CHAPTER\s+([IVXLCDM]+|\d+)\b[.\-–]*\s*(.*)$")
_RE_PART = re.compile(r"^PART\s+([IVXLCDM]+|\d+)\b[.\-–]*\s*(.*)$")
_RE_SECTION = re.compile(r"^(\d+[A-Z]{0,2})\s*\.\s*(.+)$")
_RE_SUBSECTION = re.compile(r"^\((\d+[a-z]?)\)\s*(.*)$")
_RE_ALPHA = re.compile(r"^\(([a-z]{1,2})\)\s*(.*)$")
_RE_ROMAN = re.compile(rf"^\(({ROMAN})\)\s*(.*)$")
_RE_PROVISO = re.compile(r"^(Provided\b[^,:.]*?that)\b[,:]?\s*(.*)$", re.S)
_RE_EXPLANATION = re.compile(r"^(Explanation\s*[-–.:]*\s*(?:\d+)?)\s*[-–.:]*\s*(.*)$")
_RE_SCHEDULE = re.compile(
    r"^(?:THE\s+)?((?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH)\s+)?SCHEDULE\b\s*(.*)$"
)

#: Splits "Short title and commencement.-(1) This Act ..." into heading and
#: the rest.  Indian drafting marks the end of a section heading with ".-" (or
#: ".—"); the non-greedy match stops at the first such marker, so hyphenated
#: words inside the heading ("Zone-C") survive.
_RE_SECTION_HEADING = re.compile(r"^(.{2,160}?)\s*\.\s*[-–—]\s*(.*)$", re.S)

_ALPHA_ORDER = "abcdefghijklmnopqrstuvwxyz"
_ROMAN_ORDER = [
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
]
#: Markers that are valid in both sequences and so need context to resolve.
_AMBIGUOUS = {"i", "v", "x"}


def _predecessor(list_type: str, num: str):
    """The enumerator that would come immediately before *num*, or None if
    *num* opens the sequence."""
    order = _ALPHA_ORDER if list_type == "alpha" else _ROMAN_ORDER
    try:
        index = list(order).index(num)
    except ValueError:
        return None
    return order[index - 1] if index > 0 else None


@dataclasses.dataclass
class Token:
    kind: str
    num: str = ""
    text: str = ""
    raw: str = ""
    rows: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TableBlock:
    """A table is a block element in AKN, so it lives inside <content> or
    <intro> rather than among a node's child provisions."""
    rows: list = dataclasses.field(default_factory=list)
    eid: str = ""


@dataclasses.dataclass
class Node:
    kind: str
    num: str = ""
    heading: str = ""
    subheading: str = ""
    name: str = ""                      # for hcontainer
    paragraphs: list = dataclasses.field(default_factory=list)
    wrap_paragraphs: list = dataclasses.field(default_factory=list)
    children: list = dataclasses.field(default_factory=list)
    rows: list = dataclasses.field(default_factory=list)
    list_type: str = ""                 # "alpha" | "roman" | "" (numeric)
    eid: str = ""

    def add_text(self, text: str) -> None:
        if not text:
            return
        self._target().append(text)

    def add_table(self, rows: list) -> None:
        if rows:
            self._target().append(TableBlock(rows=rows))

    def _target(self) -> list:
        return self.wrap_paragraphs if self.children else self.paragraphs

    def tables(self):
        for block in list(self.paragraphs) + list(self.wrap_paragraphs):
            if isinstance(block, TableBlock):
                yield block

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclasses.dataclass
class Schedule:
    num: str
    heading: str
    note: str = ""
    container: object = None
    eid: str = ""


@dataclasses.dataclass
class ActDocument:
    preface: list = dataclasses.field(default_factory=list)
    long_title: str = ""
    recitals: list = dataclasses.field(default_factory=list)
    enacting_formula: str = ""
    body: list = dataclasses.field(default_factory=list)
    schedules: list = dataclasses.field(default_factory=list)
    conclusions: list = dataclasses.field(default_factory=list)

    def walk(self):
        for node in self.body:
            yield from node.walk()
        for sched in self.schedules:
            if sched.container is not None:
                yield from sched.container.walk()


# =====================================================================
#  Tokenizer
# =====================================================================

class Tokenizer:
    """Classify each logical line, resolving ambiguous roman/alpha markers."""

    def tokenize(self, text: str) -> list:
        tokens = []
        for line in text.split("\n"):
            if not line.strip():
                continue
            token = self._classify(line)
            token.raw = line
            tokens.append(token)
        return self._resolve_ambiguous(tokens)

    # -- per-line classification -------------------------------------

    def _classify(self, line: str) -> Token:
        if line.startswith(TABLE_MARK):
            return Token(T_TABLE, rows=decode_table(line) or [])

        m = _RE_CHAPTER.match(line)
        if m:
            return Token(T_CHAPTER, m.group(1), m.group(2).strip())

        m = _RE_PART.match(line)
        if m:
            return Token(T_PART, m.group(1), m.group(2).strip())

        m = _RE_SCHEDULE.match(line)
        if m and line.isupper() or (m and not m.group(2).strip()):
            ordinal = (m.group(1) or "").strip()
            return Token(T_SCHEDULE, ordinal, m.group(2).strip())

        m = _RE_PROVISO.match(line)
        if m:
            return Token(T_PROVISO, "", line)

        m = _RE_EXPLANATION.match(line)
        if m:
            return Token(T_EXPLANATION, "", line)

        m = _RE_SUBSECTION.match(line)
        if m:
            return Token(T_SUBSECTION, m.group(1), m.group(2).strip())

        # Roman is tested before alpha so that "(ii)" is never read as a
        # two-letter alphabetic marker; single-letter overlaps are settled in
        # _resolve_ambiguous.
        m = _RE_ROMAN.match(line)
        if m:
            return Token(T_ROMAN, m.group(1).lower(), m.group(2).strip())

        m = _RE_ALPHA.match(line)
        if m:
            return Token(T_ALPHA, m.group(1), m.group(2).strip())

        m = _RE_SECTION.match(line)
        if m:
            return Token(T_SECTION, m.group(1), m.group(2).strip())

        if line.isupper() and len(line) > 3:
            return Token(T_HEADING, "", line)

        return Token(T_TEXT, "", line)

    # -- ambiguity resolution ----------------------------------------

    @staticmethod
    def _resolve_ambiguous(tokens: list) -> list:
        """Decide whether ``(i)``, ``(v)``, ``(x)`` continue an alpha or a
        roman list, using the nearest enumerator before and after."""
        markers = [
            i for i, t in enumerate(tokens) if t.kind in (T_ALPHA, T_ROMAN)
        ]
        for pos, idx in enumerate(markers):
            tok = tokens[idx]
            if tok.num not in _AMBIGUOUS:
                continue

            prev = tokens[markers[pos - 1]] if pos else None
            nxt = tokens[markers[pos + 1]] if pos + 1 < len(markers) else None

            alpha_pred = _ALPHA_ORDER[_ALPHA_ORDER.index(tok.num) - 1]
            roman_pred_index = _ROMAN_ORDER.index(tok.num) - 1
            roman_pred = _ROMAN_ORDER[roman_pred_index] if roman_pred_index >= 0 else None

            decided = None
            # Continues an alphabetic run: (h) -> (i), (u) -> (v), (w) -> (x).
            if prev is not None and prev.num == alpha_pred:
                decided = T_ALPHA
            # Continues a roman run: (iv) -> (v), (ix) -> (x).
            elif prev is not None and roman_pred and prev.num == roman_pred:
                decided = T_ROMAN
            # Starts a run: the next marker settles it.
            elif nxt is not None:
                succ_alpha = _ALPHA_ORDER[_ALPHA_ORDER.index(tok.num) + 1]
                succ_roman = _ROMAN_ORDER[_ROMAN_ORDER.index(tok.num) + 1]
                if nxt.num == succ_roman:
                    decided = T_ROMAN
                elif nxt.num == succ_alpha:
                    decided = T_ALPHA
            if decided is None:
                # A lone "(i)" with no neighbours is a roman list of one.
                decided = T_ROMAN
            tok.kind = decided
        return tokens


# =====================================================================
#  Tree builder
# =====================================================================

#: Element name for a list item, chosen by the kind of its parent.
_CHILD_ELEMENT = {
    "body": "section",
    "chapter": "section",
    "part": "section",
    "section": "clause",
    "subsection": "clause",
    "proviso": "clause",
    "hcontainer": "clause",
    "clause": "subclause",
    # Indian drafting nests lists further than AKN has "sub-" names for: BBMP
    # s.83(2)(b)(iii) opens a fresh (a)-(d) list four levels down.  AKN's
    # generic list elements carry those extra levels.
    "subclause": "point",
    "point": "indent",
    "indent": "indent",
    "schedule": "clause",
}

_PREFACE_MARKERS = re.compile(
    r"^(?:Ordered that|The following translation|KARNATAKA ACT|"
    r"\(First Published|\(Received the assent|NOTIFICATION|"
    r"DEPARTMENT OF|[A-Z][A-Z\s,&'()\-]{6,}$)"
)
_LONG_TITLE = re.compile(r"^An Act\b", re.I)
_RECITAL = re.compile(r"^(?:Whereas|WHEREAS|And whereas)\b")
_ENACTING = re.compile(r"^Be it enacted\b", re.I)
#: The start of the closing matter.  Deliberately narrow: a generic
#: all-capitals test would also swallow chapter headings such as "PRELIMINARY".
#: Everything after the first match is closing matter, so only the first line
#: of the signature block needs to be recognised.
_CONCLUSION = re.compile(
    r"(?:^The above translation\b|^By Order and in the name\b|"
    r"^Secretary to Government\b|\bGOVERNOR OF\b|^Sd/-|"
    # The closing publication formula of an English translation authorised
    # under Article 348(3) of the Constitution.  Only reached after the body
    # has begun, so it cannot capture the identical formula in the preface.
    r"\bArticle 348 of the Constitution\b)"
)
_SCHEDULE_NOTE = re.compile(r"^\(\s*[Ss]ee\s+(?:section|sections|rule)", re.I)


class TreeBuilder:
    """Assemble tokens into an :class:`ActDocument`."""

    def build(self, tokens: list) -> ActDocument:
        doc = ActDocument()
        body_root = Node("body")
        stack = [body_root]
        schedule = None
        in_body = False
        in_conclusions = False
        seen_enacting = False

        for tok in tokens:
            # ---- front matter -------------------------------------
            if not in_body:
                if tok.kind == T_SECTION and seen_enacting:
                    in_body = True
                elif tok.kind in (T_CHAPTER, T_PART):
                    in_body = True
                else:
                    # Front matter is kept verbatim: a "(3)" here is part of
                    # "clause (3) of Article 348", not a subsection.
                    line = tok.raw
                    if _LONG_TITLE.match(line) and not doc.long_title:
                        doc.long_title = line
                    elif _RECITAL.match(line):
                        doc.recitals.append(line)
                    elif _ENACTING.match(line):
                        doc.enacting_formula = line
                        seen_enacting = True
                    elif tok.kind == T_SUBSECTION and doc.preface:
                        doc.preface[-1] += " " + line
                    elif line:
                        doc.preface.append(line)
                    continue

            # ---- schedules and the closing formula ----------------
            if tok.kind == T_SCHEDULE:
                schedule = Schedule(num=(tok.num or "").strip(), heading="SCHEDULE")
                if tok.num:
                    schedule.heading = f"{tok.num.strip()} SCHEDULE"
                schedule.container = Node(
                    "hcontainer", name="schedule", heading=schedule.heading
                )
                doc.schedules.append(schedule)
                stack = [schedule.container]
                continue

            if schedule is not None and _SCHEDULE_NOTE.match(tok.text):
                if not schedule.container.subheading:
                    schedule.container.subheading = tok.raw
                    continue

            # The signature block ends the document.  Once it starts, every
            # remaining line is closing matter -- the Governor's name, the
            # countersignature, the publication formula -- so the flag is
            # sticky rather than re-tested line by line.
            if not in_conclusions and _CONCLUSION.search(tok.text):
                in_conclusions = True
            if in_conclusions:
                if tok.kind != T_TABLE and tok.raw.strip():
                    doc.conclusions.append(tok.raw)
                continue

            self._place(tok, stack, doc)

        doc.body = body_root.children
        return doc

    # -- placement ---------------------------------------------------

    def _place(self, tok: Token, stack: list, doc: ActDocument) -> None:
        if tok.kind == T_TABLE:
            stack[-1].add_table(tok.rows)
            return

        if tok.kind in (T_CHAPTER, T_PART):
            del stack[1:]
            node = Node(tok.kind, num=tok.num, heading=tok.text)
            stack[0].children.append(node)
            stack.append(node)
            return

        if tok.kind == T_SECTION:
            self._pop_to(stack, ("body", "chapter", "part"))
            node = Node("section", num=tok.num)
            heading, rest = self._split_heading(tok.text)
            node.heading = heading
            stack[-1].children.append(node)
            stack.append(node)
            if rest:
                self._absorb_inline(rest, stack)
            return

        if tok.kind == T_SUBSECTION:
            self._pop_to(stack, ("section", "body", "chapter", "part", "schedule"))
            node = Node("subsection", num=tok.num)
            stack[-1].children.append(node)
            stack.append(node)
            node.add_text(tok.text)
            return

        if tok.kind in (T_ALPHA, T_ROMAN):
            list_type = "alpha" if tok.kind == T_ALPHA else "roman"
            self._pop_to_list(stack, list_type, tok.num)
            parent = stack[-1]
            kind = _CHILD_ELEMENT.get(parent.kind, "clause")
            node = Node(kind, num=tok.num, list_type=list_type)
            parent.children.append(node)
            stack.append(node)
            node.add_text(tok.text)
            return

        if tok.kind in (T_PROVISO, T_EXPLANATION):
            self._pop_to(stack, ("section", "subsection", "body", "chapter", "part", "schedule"))
            if tok.kind == T_PROVISO:
                node = Node("proviso")
            else:
                node = Node("hcontainer", name="explanation")
            stack[-1].children.append(node)
            stack.append(node)
            node.add_text(tok.text)
            return

        # Plain paragraph, or an ALL-CAPS line that is a cross-heading.
        if tok.kind == T_HEADING and len(stack) > 1:
            stack[-1].add_text(tok.text)
            return
        if tok.kind == T_HEADING:
            stack[0].children.append(Node("crossHeading", heading=tok.text))
            return

        if len(stack) == 1 and stack[0].kind == "body":
            doc.conclusions.append(tok.raw)
            return
        stack[-1].add_text(tok.text)

    # -- helpers -----------------------------------------------------

    @staticmethod
    def _pop_to(stack: list, kinds: tuple) -> None:
        while len(stack) > 1 and stack[-1].kind not in kinds:
            stack.pop()

    @staticmethod
    def _pop_to_list(stack: list, list_type: str, num: str) -> None:
        """Position the stack so the new item joins the right list.

        Matching on list *type* alone is not enough, because Indian drafting
        restarts lettering at deeper levels: BBMP s.83(2) has clauses (a),(b),
        clause (b) has sub-clauses (i)-(iii), and sub-clause (iii) opens a new
        (a)-(d) list.  Rejoining the outer (a) list there would give two
        elements the same eId.

        So an item that *continues* a sequence becomes the sibling of its
        predecessor, and an item that *starts* one nests inside whatever is
        currently open.
        """
        predecessor = _predecessor(list_type, num)
        if predecessor is not None:
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].list_type == list_type and stack[i].num == predecessor:
                    del stack[i:]
                    return
            # The sequence continues but its predecessor is closed (an
            # intervening proviso, say): fall back to the innermost list of
            # this type.
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].list_type == list_type:
                    del stack[i:]
                    return
        # First item of a list: nest under the innermost open element.

    def _split_heading(self, text: str):
        """Separate a section heading from the text that follows it."""
        m = _RE_SECTION_HEADING.match(text)
        if not m:
            return "", text
        heading, rest = m.group(1).strip(), m.group(2).strip()
        # A "heading" that is really a whole sentence is not a heading.
        if len(heading.split()) > 20:
            return "", text
        return heading, rest

    def _absorb_inline(self, rest: str, stack: list) -> None:
        """Handle text that follows a section heading on the same line.

        ``1. Short title and commencement.-(1) This Act may be called ...``
        carries subsection (1) inline; it must become a real subsection rather
        than loose text on the section.
        """
        m = _RE_SUBSECTION.match(rest)
        if m:
            node = Node("subsection", num=m.group(1))
            stack[-1].children.append(node)
            stack.append(node)
            node.add_text(m.group(2).strip())
            return
        stack[-1].add_text(rest)
