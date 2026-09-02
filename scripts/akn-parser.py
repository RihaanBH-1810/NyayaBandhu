#!/usr/bin/env python3
"""
Legislative PDF -> Akoma Ntoso 3.0 XML.

This file is a thin entry point; the implementation lives in the
``akn_parser`` package next to it:

    language.py   which script/language a run of text is in
    extract.py    PDF -> single-language text (+ tables)
    normalize.py  visual lines -> one logical line per provision
    structure.py  logical lines -> a document tree
    eids.py       AKN naming-convention identifiers
    refs.py       citation detection and resolution
    meta.py       FRBR metadata
    render.py     tree -> AKN XML
    validate.py   XSD, eId, reference and language checks

Run ``python scripts/akn-parser.py --help`` for usage.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from akn_parser.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
