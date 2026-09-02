"""
Script/language detection for text extracted from bilingual Indian gazettes.

Karnataka gazettes carry the same Act twice: once in Kannada and once in an
English translation authorised under Article 348(3) of the Constitution.  The
Kannada half is encoded in one of two very different ways:

  * real Unicode Kannada (U+0C80-U+0CFF), set in fonts such as Tunga or
    Arial Unicode MS; and
  * legacy ASCII-mapped Kannada (Nudi / Baraha / BRH families), where the
    *bytes* are Latin-1 and only the font makes them render as Kannada.
    Extracted naively this looks like ``PÀ£ÁðlPÀ gÁdå ¹«¯ï``.

A byte-level filter therefore cannot separate the languages: dropping
non-ASCII throws away real Kannada while *keeping* legacy Kannada mojibake.
The reliable signal is the pair (codepoints, font family), which is what this
module classifies on.
"""
from __future__ import annotations

import re
import unicodedata

ENGLISH = "eng"
KANNADA = "kan"
NEUTRAL = "neutral"  # digits, punctuation, whitespace: belongs to either side

#: Unicode block for Kannada.
_KANNADA_CHARS = re.compile(r"[\u0C80-\u0CFF]")

#: Any Latin letter.
_LATIN_LETTERS = re.compile(r"[A-Za-z\u00C0-\u024F]")

#: Font families that render ASCII bytes as Kannada glyphs.  Matched
#: case-insensitively against the font name reported by the PDF.
_LEGACY_KANNADA_FONTS = re.compile(
    r"nudi|baraha|brh[a-z]*|shree.?lipi|akshar|kannada|kailasam|"
    r"sampige|nadanika|tunga.?ascii|kedage|malige",
    re.I,
)

#: Font families that carry genuine Unicode Kannada.  Only used to raise
#: confidence; the codepoint test above already catches these.
_UNICODE_KANNADA_FONTS = re.compile(
    r"tunga|nirmala|noto.?sans.?kannada|kedage|malige|iskoolapota|"
    r"arialunicode",
    re.I,
)

#: Characters that are structurally meaningful even inside a foreign run and
#: should never on their own make a span "foreign".
_NEUTRAL_ONLY = re.compile(r"^[\W\d_]*$", re.UNICODE)


#: How a span's characters encode its script.
#: UNICODE  - the codepoints really are the script they render as
#: LEGACY   - ASCII bytes that only a particular font turns into the script
#: SUSPECT  - nominally Unicode, but a high share of the codepoints belong to
#:            unrelated blocks, so the font's ToUnicode map is wrong
UNICODE = "unicode"
LEGACY = "legacy"
SUSPECT = "suspect"


def classify_span_detail(text: str, font: str = ""):
    """Return ``(language, encoding)`` for one PDF text span.

    ``font`` is the font name as reported by the PDF (e.g. ``Nudi01e``).
    ``encoding`` is UNICODE when the codepoints really are the script they
    render as, and LEGACY when they are ASCII bytes that only a particular
    font turns into Kannada glyphs -- text that has to be transliterated
    before it means anything.
    """
    if not text or not text.strip():
        return NEUTRAL, ""

    if _KANNADA_CHARS.search(text):
        return KANNADA, UNICODE

    has_latin = bool(_LATIN_LETTERS.search(text))

    # Legacy ASCII-mapped Kannada: Latin bytes, Kannada font.
    if has_latin and _LEGACY_KANNADA_FONTS.search(font or ""):
        return KANNADA, LEGACY

    if has_latin:
        # Mojibake heuristic for PDFs that do not report a usable font name:
        # legacy Kannada is dense in Latin-1 accented letters that English
        # legal prose never uses.
        accented = sum(1 for c in text if ord(c) > 0x7F and _LATIN_LETTERS.match(c))
        letters = sum(1 for c in text if _LATIN_LETTERS.match(c))
        if letters and accented / letters > 0.25:
            return KANNADA, LEGACY
        return ENGLISH, UNICODE

    return NEUTRAL, ""


def classify_span(text: str, font: str = "") -> str:
    """Return ENGLISH, KANNADA or NEUTRAL for one PDF text span."""
    return classify_span_detail(text, font)[0]


def is_unicode_kannada_font(font: str) -> bool:
    return bool(_UNICODE_KANNADA_FONTS.search(font or ""))


def script_letter_counts(text: str) -> dict[str, int]:
    """Count letters per script in *text*, ignoring digits and punctuation."""
    counts = {ENGLISH: 0, KANNADA: 0}
    for ch in text:
        if not unicodedata.category(ch).startswith("L"):
            continue
        if _KANNADA_CHARS.match(ch):
            counts[KANNADA] += 1
        elif _LATIN_LETTERS.match(ch):
            counts[ENGLISH] += 1
    return counts
