"""Language detection: the part a byte-level filter cannot get right."""
from akn_parser import language


def test_unicode_kannada_is_kannada():
    assert language.classify_span("ಕನಾರ್ಟಕ ರಾಜ್ಯ", "Tunga") == language.KANNADA


def test_legacy_ascii_kannada_is_kannada_not_english():
    # These bytes are Latin-1; only the Nudi font makes them Kannada.  A
    # filter that keeps ASCII would wrongly treat this as English text.
    legacy = "PÀ£ÁðlPÀ gÁdå ¹«¯ï ¸ÉÃªÉUÀ¼ÀÄ"
    assert language.classify_span(legacy, "Nudi01e") == language.KANNADA


def test_legacy_kannada_detected_without_a_font_name():
    legacy = "PÀ£ÁðlPÀ gÁdå ¹«¯ï ¸ÉÃªÉUÀ¼ÀÄ"
    assert language.classify_span(legacy, "") == language.KANNADA


def test_english_in_a_serif_font_is_english():
    assert language.classify_span(
        "Ordered that the translation of", "BookmanOldStyle"
    ) == language.ENGLISH


def test_digits_and_punctuation_are_neutral():
    # A page number set in a Kannada font must not drag the line out of the
    # English text.
    assert language.classify_span("10 ", "Nudi01kBold") == language.NEUTRAL
    assert language.classify_span(", ", "Nudi01kBold") == language.NEUTRAL
    assert language.classify_span("   ", "BookmanOldStyle") == language.NEUTRAL


def test_script_letter_counts_ignores_digits_and_punctuation():
    counts = language.script_letter_counts("Zone-C ಕನ್ನಡ 2020, (a)")
    assert counts[language.ENGLISH] == 6   # Z o n e C a
    assert counts[language.KANNADA] > 0
