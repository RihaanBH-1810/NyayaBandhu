"""
PDF -> single-language plain text (plus tables).

The extractor works at *span* level rather than page level, so a line that
mixes an English sentence with an inline Kannada bill title (very common in
the notification pages of a Karnataka gazette) still yields clean English.
Runs of text in the non-target language are preserved by default and carried
through the pipeline as opaque tokens, so the renderer can emit them tagged
with their real language and encoding rather than destroying them.  The
``--foreign`` policy selects other behaviours, including replacing each run
with an Akoma Ntoso ``<omissis/>`` marker.

Tables (schedules are almost always tables) are detected separately and
carried through the text pipeline as a single sentinel-prefixed JSON line, so
that line re-flow cannot scramble their rows.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import re

import pymupdf

from . import language, transliterate

#: Sentinel standing in for a removed foreign-language run.  U+E000 is in the
#: Private Use Area, so it can never collide with document text.
REDACTION_MARK = chr(0xE000)

#: Prefix marking a line that carries a JSON-encoded table.
TABLE_MARK = chr(0xE001)

#: Prefix marking a base64-encoded run of other-language text.
FOREIGN_MARK_TOKEN = chr(0xE002)

FOREIGN_TAG = "tag"
FOREIGN_MARK = "mark"
FOREIGN_OMIT = "omit"
FOREIGN_KEEP = "keep"
FOREIGN_POLICIES = (FOREIGN_TAG, FOREIGN_MARK, FOREIGN_OMIT, FOREIGN_KEEP)

_KANNADA_RUN = re.compile("[" + chr(0x0C80) + "-" + chr(0x0CFF) + "]+[" + chr(0x0C80) + "-" + chr(0x0CFF) + r"\s]*")


#: Codepoints XML 1.0 cannot carry.  Broken font encodings in scanned
#: gazettes emit these, and left in place they make serialisation fail
#: rather than merely look wrong.
_ILLEGAL_XML = re.compile(
    "[^"
    + chr(0x09) + chr(0x0A) + chr(0x0D)
    + chr(0x20) + "-" + chr(0xD7FF)
    + chr(0xE000) + "-" + chr(0xFFFD)
    + "]"
)


def sanitise(text: str) -> str:
    """Drop characters that cannot appear in XML character data."""
    return _ILLEGAL_XML.sub("", text)


class UnusableEncodingError(ValueError):
    """The requested language cannot be recovered from this PDF as it stands."""


#: Codepoints in the punctuation and symbol blocks that legitimately occur in
#: legislative text.  Anything else from those blocks appearing *inside* words
#: is a symptom of a broken ToUnicode map in the PDF's font.
_LEGITIMATE_SYMBOLS = frozenset(
    list(range(0x2000, 0x200C))          # spaces and joiners
    + list(range(0x2010, 0x2016))        # hyphens and dashes
    + list(range(0x2018, 0x2020))        # quotation marks
    + [0x2020, 0x2021, 0x2022, 0x2026, 0x2032, 0x2033, 0x20B9, 0x2116]
)


def misencoded_share(text: str, script_range) -> float:
    """Fraction of a script's text that came out as the wrong codepoint.

    A PDF whose font carries a partial or wrong ``ToUnicode`` map yields
    plausible-looking output in which a share of the glyphs have been mapped
    into unrelated blocks -- typically General Punctuation.  Counting those
    against the real letters of the script measures how far the text can be
    trusted.
    """
    low, high = script_range
    letters = suspicious = 0
    for ch in text:
        code = ord(ch)
        if low <= code <= high:
            letters += 1
        elif 0x2000 <= code <= 0x2BFF and code not in _LEGITIMATE_SYMBOLS:
            suspicious += 1
    total = letters + suspicious
    return suspicious / total if total else 0.0


@dataclasses.dataclass
class _ForeignRun:
    """An open run of text in a language other than the requested one."""
    lang: str
    encoding: str
    font_encoding: str
    text: str = ""

    def matches(self, other) -> bool:
        return (self.lang, self.encoding, self.font_encoding) == (
            other.lang, other.encoding, other.font_encoding
        )


@dataclasses.dataclass
class PageStats:
    number: int
    target_letters: int
    foreign_letters: int
    kept: bool
    reason: str = ""
    tables: int = 0

    @property
    def target_ratio(self) -> float:
        total = self.target_letters + self.foreign_letters
        return self.target_letters / total if total else 0.0


@dataclasses.dataclass
class ExtractionResult:
    text: str
    pages: list[PageStats]
    redactions: int

    @property
    def kept_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.kept]


def encode_foreign(text: str, lang: str, encoding: str, font_encoding: str) -> str:
    """Wrap a run of other-language text as an opaque, whitespace-safe token.

    The payload is base64 so that the later text pipeline -- which collapses
    whitespace and re-flows lines -- cannot alter the text it carries.
    """
    payload = json.dumps(
        {"t": text, "l": lang, "e": encoding, "f": font_encoding},
        ensure_ascii=False,
    )
    blob = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{FOREIGN_MARK_TOKEN}{blob}{FOREIGN_MARK_TOKEN}"


def decode_foreign(token: str):
    """Decode a token produced by :func:`encode_foreign`, or return None."""
    stripped = token.strip(FOREIGN_MARK_TOKEN)
    try:
        payload = base64.urlsafe_b64decode(stripped.encode("ascii")).decode("utf-8")
        data = json.loads(payload)
    except Exception:
        return None
    return data["t"], data["l"], data["e"], data.get("f", "nudi")


def encode_table(rows: list[list[str]]) -> str:
    return TABLE_MARK + json.dumps(rows, ensure_ascii=False)


def decode_table(line: str):
    if not line.startswith(TABLE_MARK):
        return None
    return json.loads(line[len(TABLE_MARK):])


class TextExtractor:
    """Pull the text of one language out of a (possibly bilingual) PDF."""

    def __init__(
        self,
        target_lang: str = language.ENGLISH,
        foreign_policy: str = FOREIGN_TAG,
        min_page_letters: int = 200,
        min_page_ratio: float = 0.55,
        detect_tables: bool = True,
    ):
        if foreign_policy not in FOREIGN_POLICIES:
            raise ValueError(f"foreign_policy must be one of {FOREIGN_POLICIES}")
        self.target_lang = target_lang
        self.foreign_policy = foreign_policy
        self.min_page_letters = min_page_letters
        self.min_page_ratio = min_page_ratio
        self.detect_tables = detect_tables
        self.redactions = 0
        self.legacy_letters = 0
        self.unicode_letters = 0

    # -- public API --------------------------------------------------

    def extract(self, pdf_path: str) -> ExtractionResult:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(pdf_path)

        self.redactions = 0
        self.legacy_letters = self.unicode_letters = 0
        doc = pymupdf.open(pdf_path)
        page_texts: list[str] = []
        stats: list[PageStats] = []

        for pno in range(len(doc)):
            text, tgt, foreign, ntables = self._page_text(doc.load_page(pno))
            st = PageStats(pno, tgt, foreign, kept=False, tables=ntables)
            if tgt < self.min_page_letters:
                st.reason = f"only {tgt} {self.target_lang} letters"
            elif st.target_ratio < self.min_page_ratio:
                st.reason = (
                    f"{self.target_lang} share {st.target_ratio:.0%} below threshold"
                )
            else:
                st.kept = True
            stats.append(st)
            page_texts.append(text)

        doc.close()

        kept = [i for i, s in enumerate(stats) if s.kept]
        if not kept:
            raise ValueError(
                f"No page of {os.path.basename(pdf_path)} carries enough "
                f"{self.target_lang!r} text (checked {len(stats)} pages). "
                f"Is --lang set correctly?"
            )

        # A translated Act occupies a contiguous run of pages; re-admitting the
        # gaps inside that run keeps table-heavy pages, which fall below the
        # letter threshold, from being dropped out of the middle of the Act.
        for pno in range(kept[0], kept[-1] + 1):
            if not stats[pno].kept:
                stats[pno].kept = True
                stats[pno].reason = "re-admitted: inside the main run of pages"

        body = "\n".join(page_texts[i] for i, s in enumerate(stats) if s.kept)
        self._check_encoding(pdf_path, body)
        return ExtractionResult(body, stats, self.redactions)

    def _check_encoding(self, pdf_path: str, body: str) -> None:
        """Refuse to emit text that is mojibake rather than the language asked for.

        Two things go wrong with the Kannada half of a Karnataka gazette from
        this period, and both produce output that would validate as XML and be
        nonsense as law, so neither is worth writing to disk silently.
        """
        name = os.path.basename(pdf_path)

        total = self.legacy_letters + self.unicode_letters
        if total and self.legacy_letters / total >= 0.5:
            raise UnusableEncodingError(
                f"{name}: {self.legacy_letters / total:.0%} of the "
                f"'{self.target_lang}' text is set in a legacy ASCII-mapped "
                f"font (the Nudi/Baraha family), which maps Kannada glyphs "
                f"onto Latin-1 bytes -- what comes out is 'PÀ£ÁðlPÀ gÁdå', "
                f"not 'ಕರ್ನಾಟಕ ರಾಜ್ಯ'. Recovering it needs a font-specific "
                f"transliteration step, which this parser does not have yet. "
                f"Use --lang eng for this document, or --foreign keep to "
                f"inspect the raw bytes."
            )

        if self.target_lang == language.KANNADA:
            share = misencoded_share(body, (0x0C80, 0x0CFF))
            if share >= 0.05:
                raise UnusableEncodingError(
                    f"{name}: {share:.0%} of the Kannada characters came out "
                    f"as unrelated codepoints (mostly General Punctuation), "
                    f"which means the font's ToUnicode map is wrong or "
                    f"incomplete. Roughly one letter in "
                    f"{max(2, round(1 / share))} would be incorrect. The text "
                    f"has to be repaired -- by OCR or by a font-specific "
                    f"mapping -- before it can be marked up. Use --lang eng "
                    f"for this document in the meantime."
                )

    # -- internals ---------------------------------------------------

    def _page_text(self, page):
        table_boxes = []
        tables = []
        if self.detect_tables:
            for tab in page.find_tables().tables:
                rows = self._clean_rows(tab.extract())
                if len(rows) < 2:
                    continue
                table_boxes.append(pymupdf.Rect(tab.bbox))
                tables.append((tab.bbox[1], encode_table(rows)))

        blocks = [b for b in page.get_text("dict")["blocks"] if "lines" in b]
        blocks = self._reading_order(blocks, page.rect.width)

        items = list(tables)
        target_letters = foreign_letters = 0

        for block in blocks:
            block_lines = []
            for line in block["lines"]:
                # Filtering at line level rather than block level matters: a
                # text block can start inside a table and run on past it, and
                # dropping the whole block would lose the text that follows.
                if self._inside(line["bbox"], table_boxes):
                    continue
                joined, tgt, foreign = self._line_text(line)
                target_letters += tgt
                foreign_letters += foreign
                if joined.strip():
                    block_lines.append(joined)
            if block_lines:
                items.append((block["bbox"][1], "\n".join(block_lines)))

        for _, payload in tables:
            for row in decode_table(payload) or []:
                for cell in row:
                    counts = language.script_letter_counts(cell)
                    target_letters += counts.get(self.target_lang, 0)
                    foreign_letters += sum(
                        v for k, v in counts.items() if k != self.target_lang
                    )

        items.sort(key=lambda it: it[0])
        text = "\n".join(p for _, p in items)
        return text, target_letters, foreign_letters, len(tables)

    def _line_text(self, line: dict):
        pieces = []
        pending = None          # an open run of other-language spans
        target_letters = foreign_letters = 0

        for span in line["spans"]:
            text = sanitise(span["text"])
            if not text:
                continue
            font = span.get("font", "")
            lang, encoding = language.classify_span_detail(text, font)
            counts = language.script_letter_counts(text)

            if lang == self.target_lang and encoding == language.LEGACY:
                self.legacy_letters += sum(1 for c in text if c.isalpha())
            elif lang == self.target_lang:
                self.unicode_letters += counts.get(self.target_lang, 0)

            if lang in (self.target_lang, language.NEUTRAL):
                if pending is not None:
                    pieces.append(self._close_foreign(pending))
                    pending = None
                pieces.append(text)
                target_letters += counts.get(self.target_lang, 0)
                continue

            foreign_letters += sum(counts.values())

            if self.foreign_policy == FOREIGN_KEEP:
                pieces.append(text)
            elif self.foreign_policy == FOREIGN_OMIT:
                pass
            else:
                run = _ForeignRun(lang, encoding,
                                  transliterate.encoding_for_font(font))
                # Adjacent spans of the same language and encoding are one
                # passage, not several: the gazette breaks a title across
                # spans wherever the typesetter changed size or weight.
                if pending is not None and pending.matches(run):
                    pending.text += text
                else:
                    if pending is not None:
                        pieces.append(self._close_foreign(pending))
                    run.text = text
                    pending = run

        if pending is not None:
            pieces.append(self._close_foreign(pending))

        return "".join(pieces).rstrip(), target_letters, foreign_letters

    #: Above this share of wrong codepoints, a run is reported as misencoded
    #: rather than as clean Unicode.
    SUSPECT_THRESHOLD = 0.05

    def _close_foreign(self, run) -> str:
        """Emit an open run of other-language text under the current policy."""
        self.redactions += 1
        if self.foreign_policy == FOREIGN_MARK:
            return f" {REDACTION_MARK} "

        encoding = run.encoding
        if encoding == language.UNICODE and run.lang == language.KANNADA:
            if misencoded_share(run.text, (0x0C80, 0x0CFF)) >= self.SUSPECT_THRESHOLD:
                encoding = language.SUSPECT
        return encode_foreign(run.text, run.lang, encoding, run.font_encoding)

    def _foreign_placeholder(self) -> str:
        self.redactions += 1
        return f" {REDACTION_MARK} "

    def _clean_rows(self, rows):
        """Normalise a detected table: drop empty rows, merge wrapped rows.

        ``find_tables`` reports empty cells as None, and a row whose first cell
        is empty is the continuation of the row above -- very common where a
        long schedule entry wraps across a page break.
        """
        out = []
        for raw in rows:
            cells = [self._clean_cell(c) for c in raw]
            if not any(cells):
                continue
            if out and not cells[0] and len(cells) == len(out[-1]):
                for i, cell in enumerate(cells):
                    if cell:
                        out[-1][i] = (out[-1][i] + " " + cell).strip()
                continue
            out.append(cells)
        return out

    def _clean_cell(self, cell) -> str:
        text = re.sub(r"\s+", " ", sanitise(cell or "")).strip()
        if self.target_lang != language.KANNADA and _KANNADA_RUN.search(text):
            if self.foreign_policy != FOREIGN_KEEP:
                replacement = (
                    f" {REDACTION_MARK} "
                    if self.foreign_policy == FOREIGN_MARK
                    else " "
                )
                text = _KANNADA_RUN.sub(replacement, text)
                self.redactions += 1
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _inside(bbox, boxes) -> bool:
        if not boxes:
            return False
        rect = pymupdf.Rect(bbox)
        centre = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        return any(centre in box for box in boxes)

    @staticmethod
    def _reading_order(blocks, page_width: float):
        """Sort blocks top-to-bottom, honouring a two-column layout if present.

        Bilingual gazettes set Kannada and English side by side on cover
        pages; without this the two columns interleave line by line.
        """
        if not blocks:
            return blocks
        mid = page_width / 2
        left = [b for b in blocks if b["bbox"][2] <= mid + page_width * 0.05]
        right = [b for b in blocks if b["bbox"][0] >= mid - page_width * 0.05]
        straddling = [b for b in blocks if b not in left and b not in right]

        # Only treat the page as two-column when both columns are substantial
        # and little text crosses the gutter.
        if len(left) >= 3 and len(right) >= 3 and len(straddling) <= len(blocks) * 0.2:
            ordered = sorted(straddling, key=lambda b: b["bbox"][1])
            ordered += sorted(left, key=lambda b: b["bbox"][1])
            ordered += sorted(right, key=lambda b: b["bbox"][1])
            return ordered

        return sorted(blocks, key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))
