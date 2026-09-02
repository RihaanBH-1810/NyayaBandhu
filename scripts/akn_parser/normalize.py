"""
Turn raw per-visual-line PDF output into one logical line per provision.

The previous implementation joined a line to its predecessor unless the
predecessor ended in punctuation.  That gets Indian legislative text wrong in
both directions: wrapped lines routinely end in a comma (and were wrongly
split), and a new proviso routinely follows a colon (and was wrongly joined).
Here the decision is driven by the *current* line instead -- a line starts a
new logical line only when it opens a recognised structural unit.  Matching is
case sensitive on purpose: ``NOTIFICATION`` is a gazette heading whereas
``notification, appoint.`` is the tail of a wrapped sentence.
"""
from __future__ import annotations

import re

from .extract import (
    FOREIGN_MARK_TOKEN,
    REDACTION_MARK,
    TABLE_MARK,
    decode_foreign,
    encode_foreign,
)

#: Roman numerals i..xxxix, as used for clause numbering.
ROMAN = r"(?:x{0,3}(?:ix|iv|v?i{0,3}))"

#: A line that opens a new structural unit.  Case sensitive.
STRUCTURAL_START = re.compile(
    r"^(?:"
    r"(?:CHAPTER|PART|BOOK|TITLE)\s+[IVXLCDM0-9]+\b"
    r"|(?:THE\s+)?(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH)?\s*SCHEDULE\b"
    r"|\d+[A-Z]?\s*\.\s*[A-Z(]"                   # 1. / 12A. section
    r"|\(\d+[a-z]?\)"                             # (1) subsection
    r"|\([a-z]{1,2}\)"                            # (a) clause
    rf"|\({ROMAN}\)"                              # (i) clause / sub-clause
    r"|Provided\b"
    r"|Explanation\b"
    r"|Whereas\b"
    r"|WHEREAS\b"
    r"|Be\s+it\s+enacted\b"
    r"|An\s+Act\s+to\b"
    r"|\([Ss]ee\s+(?:section|sections|rule)"
    r")"
)

#: An all-capitals line (act titles, chapter headings, department names).
ALL_CAPS = re.compile(r"^[^a-z]*[A-Z][^a-z]*$")

#: A line ending on the keyword of a citation, so that the "(1)" opening the
#: next line is that citation's number and not a new subsection.  BBMP s.11
#: wraps as "... under clause (b) of sub-section" / "(1) of section 8 shall...".
_CITATION_TAIL = re.compile(
    r"(?:sub[-\s]?sections?|sub[-\s]?clauses?|sub[-\s]?rules?|sections?"
    r"|clauses?|paragraphs?|articles?|rules?|items?)\s*$",
    re.I,
)

#: An enumerator followed by a word that no provision ever opens with.
_CITATION_HEAD = re.compile(
    rf"^\((?:\d+[a-z]?|[a-z]{{1,2}}|{ROMAN})\)\s+(?:of|to|and|or|read)\b"
)

#: Punctuation that genuinely closes a provision.
_TERMINAL = re.compile(r"[.;:\-]\s*$")

#: Codepoints that are not legal in XML 1.0 character data.
_CONTROL_CHARS = re.compile(
    "[^"
    + chr(0x09) + chr(0x0A) + chr(0x0D)
    + chr(0x20) + "-" + chr(0xD7FF)
    + chr(0xE000) + "-" + chr(0xFFFD)
    + "]"
)

#: A line consisting only of a stranded enumerator, e.g. "(i)" or "3." sitting
#: alone in a table cell; it belongs to the line that follows.
ORPHAN_ENUMERATOR = re.compile(
    rf"^(?:\d{{1,3}}\.?|[A-Z]\.|[IVXLCDM]{{1,5}}\.?|\([a-z]\)|\(\d+\)|\({ROMAN}\)|[a-z]\.)$"
)

#: Standalone page numbers and gazette running furniture.
_PAGE_FURNITURE = re.compile(
    r"^(?:\d{1,4}"
    r"|Part\s*[-–]?\s*[IVXLC]+[A-Z]?"
    r"|R\.N\.I\..*"
    r"|POSTAL\s+REGN.*"
    r"|Licensed\s+to\s+post.*"
    r"|RNP/.*"
    r"|WPP\s*No.*"
    r"|Digitally\s+signed\s+by.*"
    r"|Date:\s*\d{4}\.\d{2}\.\d{2}.*"
    r")\s*$",
    re.I,
)


class TextNormalizer:
    """Clean, de-hyphenate and re-flow extracted text."""

    def run(self, raw: str) -> str:
        text = self._clean(raw)
        text = self._dehyphenate(text)
        lines = [ln.strip() for ln in text.split("\n")]
        lines = [ln for ln in lines if ln]
        lines = self._drop_furniture(lines)
        lines = self._stitch_orphans(lines)
        lines = self._reflow(lines)
        lines = self._merge_tables(lines)
        lines = self._drop_empty_after_redaction(lines)
        lines = [self._merge_foreign_runs(ln) for ln in lines]
        return "\n".join(lines)

    # -- internals ---------------------------------------------------

    @staticmethod
    def _clean(text: str) -> str:
        # Drop characters XML cannot carry.  Scanned gazettes pick these up
        # from broken font encodings; left in place they make serialisation
        # fail rather than merely look wrong.
        text = _CONTROL_CHARS.sub("", text)
        # Collapse runs of redaction marks: adjacent foreign spans each produce
        # a mark, but together they are a single omitted passage.
        text = re.sub(rf"(?:[ \t]*{REDACTION_MARK}[ \t]*)+", f" {REDACTION_MARK} ", text)
        # Normalise the typographic characters gazettes use inconsistently.
        text = text.replace("‐", "-").replace("‑", "-")
        text = text.replace("‘", "'").replace("’", "'")
        text = text.replace("“", '"').replace("”", '"')
        text = re.sub(r"[   ]", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"\n{2,}", "\n", text)

    @staticmethod
    def _dehyphenate(text: str) -> str:
        """Rejoin words split across a line break by a soft hyphen.

        Only applied when the next line starts lowercase, so that genuinely
        hyphenated compounds at a line end (``pupil-\\nteacher``) survive and
        list dashes are untouched.
        """
        return re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)

    @staticmethod
    def _drop_furniture(lines):
        return [
            ln
            for ln in lines
            if ln.startswith(TABLE_MARK) or not _PAGE_FURNITURE.match(ln)
        ]

    @staticmethod
    def _stitch_orphans(lines):
        out = []
        pending = ""
        for ln in lines:
            if ln.startswith(TABLE_MARK):
                if pending:
                    out.append(pending.strip())
                    pending = ""
                out.append(ln)
                continue
            if ORPHAN_ENUMERATOR.match(ln):
                pending += ln + " "
                continue
            out.append(pending + ln if pending else ln)
            pending = ""
        if pending:
            out.append(pending.strip())
        return out

    @staticmethod
    def _reflow(lines):
        joined = []
        for ln in lines:
            if ln.startswith(TABLE_MARK) or not joined or joined[-1].startswith(TABLE_MARK):
                joined.append(ln)
                continue
            prev = joined[-1]
            starts_unit = bool(STRUCTURAL_START.match(ln))
            if starts_unit and TextNormalizer._continues_citation(prev, ln):
                starts_unit = False
            caps = bool(ALL_CAPS.match(ln))
            prev_caps = bool(ALL_CAPS.match(prev))
            if caps and prev_caps and not starts_unit:
                # Consecutive all-caps lines are one wrapped heading.
                joined[-1] = joined[-1] + " " + ln
            elif starts_unit or caps != prev_caps:
                joined.append(ln)
            else:
                joined[-1] = joined[-1] + " " + ln
        return [
            ln if ln.startswith(TABLE_MARK) else re.sub(r"\s+", " ", ln).strip()
            for ln in joined
        ]

    @staticmethod
    def _continues_citation(prev: str, line: str) -> bool:
        """True when *line*'s leading enumerator belongs to a citation that
        began on *prev* rather than opening a new provision."""
        if _CITATION_TAIL.search(prev):
            return True
        return bool(_CITATION_HEAD.match(line)) and not _TERMINAL.search(prev)

    @staticmethod
    def _drop_empty_after_redaction(lines):
        """Discard lines that held nothing but foreign-language text.

        The printer's colophon at the foot of a Karnataka gazette is entirely
        Kannada; once redacted it is a row of markers and punctuation, which is
        noise rather than an omission worth recording.
        """
        out = []
        for ln in lines:
            if ln.startswith(TABLE_MARK):
                out.append(ln)
                continue
            stripped = ln.replace(REDACTION_MARK, "")
            if REDACTION_MARK in ln and not re.search(r"[A-Za-z]{2}", stripped):
                continue
            # Collapse markers that ended up adjacent after re-flow.
            out.append(re.sub(rf"(?:{REDACTION_MARK}[\s,;.]*)+", REDACTION_MARK + " ",
                              ln).strip())
        return out

    @staticmethod
    def _merge_foreign_runs(line: str) -> str:
        """Join adjacent other-language tokens into one run.

        A title that wrapped across two lines in the gazette arrives as two
        tokens; once the lines have been re-flowed they are one passage again,
        and should be tagged as one element rather than two.
        """
        if FOREIGN_MARK_TOKEN not in line:
            return line

        pattern = re.compile(
            f"{FOREIGN_MARK_TOKEN}([A-Za-z0-9_=-]+){FOREIGN_MARK_TOKEN}"
            r"(\s*)"
            f"{FOREIGN_MARK_TOKEN}([A-Za-z0-9_=-]+){FOREIGN_MARK_TOKEN}"
        )

        def join(match):
            left = decode_foreign(FOREIGN_MARK_TOKEN + match.group(1) + FOREIGN_MARK_TOKEN)
            right = decode_foreign(FOREIGN_MARK_TOKEN + match.group(3) + FOREIGN_MARK_TOKEN)
            if left is None or right is None or left[1:] != right[1:]:
                return match.group(0)
            gap = match.group(2)
            if not gap and not left[0].endswith(" ") and not right[0].startswith(" "):
                gap = " "
            return encode_foreign(left[0] + gap + right[0], *left[1:])

        previous = None
        while previous != line:
            previous = line
            line = pattern.sub(join, line)
        return line

    @staticmethod
    def _merge_tables(lines):
        """Join tables split across a page break into one table."""
        import json

        out = []
        for ln in lines:
            if ln.startswith(TABLE_MARK) and out and out[-1].startswith(TABLE_MARK):
                prev = json.loads(out[-1][len(TABLE_MARK):])
                cur = json.loads(ln[len(TABLE_MARK):])
                if prev and cur and len(prev[0]) == len(cur[0]):
                    # A continuation row (empty first cell) belongs to the last
                    # row of the previous page's table.
                    if not cur[0][0]:
                        for i, cell in enumerate(cur[0]):
                            if cell:
                                prev[-1][i] = (prev[-1][i] + " " + cell).strip()
                        cur = cur[1:]
                    out[-1] = TABLE_MARK + json.dumps(prev + cur, ensure_ascii=False)
                    continue
            out.append(ln)
        return out
