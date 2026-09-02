import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

TEACHERS_PDF = os.path.join(
    REPO_ROOT, "data", "v0s", "kan_eng", "tranfer_of_teachers.pdf"
)


@pytest.fixture(scope="session")
def teachers():
    """The Teachers Transfer Act, parsed once for the whole session."""
    if not os.path.exists(TEACHERS_PDF):
        pytest.skip(f"missing fixture PDF: {TEACHERS_PDF}")
    from akn_parser.pipeline import ActParser

    return ActParser().parse(TEACHERS_PDF)


@pytest.fixture(scope="session")
def teachers_xml(teachers):
    from lxml import etree

    return etree.fromstring(teachers.xml)
