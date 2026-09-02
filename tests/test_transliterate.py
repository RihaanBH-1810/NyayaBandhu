"""
Preserving, tagging and converting text in another language.

The parser does not delete text it was not asked for: it keeps it, records
what language it is in, and records whether the codepoints have been converted
out of a legacy font encoding yet.
"""
import pytest

from akn_parser import language, transliterate
from akn_parser.extract import decode_foreign, encode_foreign
from akn_parser.refs import CitationResolver


NUDI_TITLE = "PÀ£ÁðlPÀ gÁdå ¹«¯ï ¸ÉÃªÉUÀ¼ÀÄ"


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    transliterate.unregister(language.KANNADA, "nudi")


# -- BCP-47 tagging ---------------------------------------------------

def test_unicode_text_is_tagged_with_the_bare_language():
    assert transliterate.bcp47(language.KANNADA, language.UNICODE) == "kn"


def test_legacy_text_declares_its_script_and_encoding():
    # Kannada stored as Latin-1 bytes for a Nudi font: the language is
    # Kannada, but the codepoints really are Latin.
    assert (
        transliterate.bcp47(language.KANNADA, language.LEGACY, "nudi")
        == "kn-Latn-x-nudi"
    )


def test_misencoded_text_is_distinguished_from_clean_text():
    # Right script, wrong codepoints: this needs repair, not transliteration.
    assert (
        transliterate.bcp47(language.KANNADA, language.SUSPECT)
        == "kn-x-misencoded"
    )


@pytest.mark.parametrize(
    "font,encoding",
    [("Nudi01e", "nudi"), ("BRH Kannada", "nudi"), ("ShreeLipi", "shreelipi"),
     ("Tunga", "nudi")],
)
def test_encoding_is_identified_from_the_font(font, encoding):
    assert transliterate.encoding_for_font(font) == encoding


# -- the converter hook -----------------------------------------------

def convert(text=NUDI_TITLE, encoding=None, font_encoding="nudi"):
    """Call convert() exactly as the renderer does, from a Segment."""
    return transliterate.convert(
        text, language.KANNADA, encoding or language.LEGACY, font_encoding
    )


def test_text_is_preserved_verbatim_when_no_converter_is_registered():
    assert convert() == (NUDI_TITLE, language.LEGACY)


def test_a_registered_converter_is_used_and_flips_the_encoding():
    transliterate.register(language.KANNADA, "nudi", lambda t: "ಕರ್ನಾಟಕ")
    text, encoding = convert()
    assert text == "ಕರ್ನಾಟಕ"
    assert encoding == language.UNICODE
    assert transliterate.bcp47(language.KANNADA, encoding) == "kn"


def test_the_converter_is_chosen_by_font_encoding_not_by_codepoint_state():
    # "legacy" is the state of the codepoints; "nudi" is the glyph layout.
    # Confusing the two silently disables every registered converter.
    transliterate.register(language.KANNADA, "nudi", lambda t: "ಕನ್ನಡ")
    assert convert(font_encoding="nudi")[1] == language.UNICODE
    assert convert(font_encoding="shreelipi")[1] == language.LEGACY


def test_a_converter_that_fails_leaves_the_text_untouched():
    # Half-converted legal text is worse than unconverted legal text.
    def broken(text):
        raise ValueError("no mapping for this glyph")

    transliterate.register(language.KANNADA, "nudi", broken)
    assert convert() == (NUDI_TITLE, language.LEGACY)


def test_a_converter_that_declines_leaves_the_text_untouched():
    transliterate.register(language.KANNADA, "nudi", lambda t: None)
    assert convert() == (NUDI_TITLE, language.LEGACY)


def test_already_unicode_text_is_never_passed_to_a_converter():
    transliterate.register(language.KANNADA, "nudi", lambda t: "WRONG")
    assert convert("ಕನ್ನಡ", language.UNICODE) == ("ಕನ್ನಡ", language.UNICODE)


def test_misencoded_text_is_never_passed_to_a_converter():
    # Its codepoints are already Kannada; it needs repair, not transliteration.
    transliterate.register(language.KANNADA, "nudi", lambda t: "WRONG")
    assert convert("ಕನ⁏ನಡ", language.SUSPECT) == ("ಕನ⁏ನಡ", language.SUSPECT)


# -- carrying runs through the text pipeline --------------------------

def test_a_foreign_run_survives_encoding_and_decoding():
    token = encode_foreign(NUDI_TITLE, language.KANNADA, language.LEGACY, "nudi")
    assert decode_foreign(token) == (NUDI_TITLE, language.KANNADA, language.LEGACY, "nudi")


def test_the_token_is_opaque_to_whitespace_collapsing():
    # The normaliser collapses runs of whitespace; the payload must not be
    # altered by that, so it carries no spaces.
    token = encode_foreign("a  b\tc", language.KANNADA, language.LEGACY, "nudi")
    assert " " not in token and "\t" not in token
    assert decode_foreign(token)[0] == "a  b\tc"


def test_the_resolver_turns_a_token_into_a_foreign_segment():
    token = encode_foreign(NUDI_TITLE, language.KANNADA, language.LEGACY, "nudi")
    segments = CitationResolver({}).markup(f"translation of {token} in English", "")
    kinds = [s.kind for s in segments]
    assert "foreign" in kinds
    foreign = next(s for s in segments if s.kind == "foreign")
    assert foreign.text == NUDI_TITLE
    assert (foreign.lang, foreign.encoding) == (language.KANNADA, language.LEGACY)
