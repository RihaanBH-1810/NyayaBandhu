"""
Conversion of legacy font encodings to Unicode.

Kannada in Karnataka gazettes of this period is often typeset in Nudi or
Baraha fonts, which store glyph codes in Latin-1 bytes rather than characters:
the PDF yields ``PÀ£ÁðlPÀ gÁdå`` where the text is ``ಕರ್ನಾಟಕ ರಾಜ್ಯ``.

Converting that back is a real transformation, not a byte substitution. It
needs a glyph table plus reordering rules for dependent vowels, vattakshara
and legacy symbol combinations, and getting it subtly wrong produces Kannada
that looks plausible and says something else. **No converter ships with this
parser**, because a table that has not been checked by someone who reads
Kannada would be worse than no table at all: it would turn a visibly broken
document into an invisibly wrong one.

Instead this module defines the interface. Register a verified converter and
every legacy run in every document is converted on the next run; register
nothing and those runs are preserved verbatim and tagged
``kn-Latn-x-nudi``, so they remain findable and convertible later.

Registering a converter
-----------------------

::

    from akn_parser import transliterate

    def nudi_to_unicode(text: str) -> str:
        ...

    transliterate.register("kan", "nudi", nudi_to_unicode)

Known implementations that could be adapted (check their licences before
vendoring):

* ``aravindavk/ascii2unicode`` -- Python 3, supports Nudi and Baraha
* ``looped-labs/asciikannada2unicode`` -- Java
* Sanka, https://aravindavk.in/sanka/ -- browser tool by the same author

A converter must be a pure function of its input, must return Unicode text in
the target script, and must raise or return ``None`` if it cannot convert the
input, rather than returning a partial result.
"""
from __future__ import annotations

from . import language

#: (target language, legacy encoding name) -> converter callable.
_CONVERTERS: dict = {}

#: Font-family fragment -> the legacy encoding it implements.  Used to pick a
#: converter and to build the BCP-47 private-use subtag.
LEGACY_ENCODINGS = (
    ("nudi", "nudi"),
    ("baraha", "nudi"),        # Baraha shares the Nudi/GoK glyph layout
    ("brh", "nudi"),
    ("shree", "shreelipi"),
    ("akshar", "akruti"),
    ("akruti", "akruti"),
)

DEFAULT_ENCODING = "nudi"


def register(lang: str, encoding: str, converter) -> None:
    """Register a converter for one language and legacy encoding."""
    _CONVERTERS[(lang, encoding)] = converter


def unregister(lang: str, encoding: str) -> None:
    _CONVERTERS.pop((lang, encoding), None)


def available(lang: str, encoding: str) -> bool:
    return (lang, encoding) in _CONVERTERS


def encoding_for_font(font: str) -> str:
    """Name the legacy encoding a font implements."""
    lowered = (font or "").lower()
    for fragment, encoding in LEGACY_ENCODINGS:
        if fragment in lowered:
            return encoding
    return DEFAULT_ENCODING


def convert(text: str, lang: str, encoding: str,
            font_encoding: str = DEFAULT_ENCODING):
    """Convert *text* out of a legacy encoding.

    Two different things are called "encoding" here and they are not
    interchangeable.  ``encoding`` is the *state* of the codepoints -- one of
    UNICODE, LEGACY, SUSPECT -- and decides **whether** conversion applies.
    ``font_encoding`` names the legacy glyph layout (``nudi``, ``shreelipi``)
    and decides **which** converter to use.

    Returns ``(text, encoding)``. When no converter is registered, or the
    registered one declines the input, the text is returned unchanged with its
    encoding still reported as legacy, so callers can tag it accurately.
    """
    if encoding != language.LEGACY:
        return text, encoding

    converter = _CONVERTERS.get((lang, font_encoding))
    if converter is None:
        return text, language.LEGACY

    try:
        converted = converter(text)
    except Exception:
        return text, language.LEGACY
    if not converted:
        return text, language.LEGACY
    return converted, language.UNICODE


def bcp47(lang: str, encoding: str, legacy_encoding: str = DEFAULT_ENCODING) -> str:
    """Build the BCP-47 tag describing a run of text.

    Unicode Kannada is simply ``kn``. Kannada stored as Latin-1 bytes for a
    Nudi font is ``kn-Latn-x-nudi``: the language, the script the codepoints
    actually belong to, and a private-use subtag naming the encoding. A
    consumer can therefore tell converted text from unconverted text without
    inspecting the characters.
    """
    subtag = ISO639_1.get(lang, lang)
    if encoding == language.UNICODE:
        return subtag
    if encoding == language.SUSPECT:
        # Correct script, wrong codepoints: the text needs repair, not
        # transliteration, and a consumer must not treat it as clean Kannada.
        return f"{subtag}-x-misencoded"
    return f"{subtag}-Latn-x-{legacy_encoding}"


#: Internal language keys to the BCP-47 / ISO 639-1 codes used in xml:lang.
#: Note this is deliberately distinct from the three-letter ISO 639-2 codes
#: used in FRBR expression URIs, where AKN requires the longer form.
ISO639_1 = {
    language.ENGLISH: "en",
    language.KANNADA: "kn",
}
