"""
The parser refuses to emit text it cannot actually read.

Both failure modes below produce output that is well-formed XML and valid
Akoma Ntoso while being nonsense as law, which is the worst possible outcome
for a corpus meant to be authoritative.
"""
import pytest

from akn_parser.extract import (
    TextExtractor,
    UnusableEncodingError,
    misencoded_share,
)
from conftest import TEACHERS_PDF


def test_misencoded_share_is_zero_for_clean_text():
    assert misencoded_share("ಕರ್ನಾಟಕ ರಾಜ್ಯ", (0x0C80, 0x0CFF)) == 0.0


def test_misencoded_share_counts_glyphs_mapped_into_other_blocks():
    # U+204F and U+2044 are what a broken ToUnicode map emits in place of
    # Kannada letters in these gazettes.
    assert misencoded_share("ಕರ⁏ನಾ⁄ಟಕ", (0x0C80, 0x0CFF)) > 0.2


def test_legitimate_dashes_and_quotes_are_not_counted():
    assert misencoded_share("ಕರ–ನಾಟಕ ‘ರಾಜ್ಯ’", (0x0C80, 0x0CFF)) == 0.0


def test_kannada_extraction_refuses_rather_than_emitting_mojibake():
    import os

    if not os.path.exists(TEACHERS_PDF):
        pytest.skip("missing fixture PDF")
    with pytest.raises(UnusableEncodingError) as excinfo:
        TextExtractor(target_lang="kan").extract(TEACHERS_PDF)
    assert "--lang eng" in str(excinfo.value)


def test_english_extraction_from_the_same_pdf_is_unaffected():
    import os

    if not os.path.exists(TEACHERS_PDF):
        pytest.skip("missing fixture PDF")
    result = TextExtractor(target_lang="eng").extract(TEACHERS_PDF)
    assert "Karnataka State Civil Services" in result.text
