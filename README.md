# NyayaBandhu

Digital Public Infrastructure for Indian legislative documents. NyayaBandhu
standardises legislative text into [Akoma Ntoso](https://www.oasis-open.org/committees/legaldocml/)
(OASIS LegalDocML), replacing fragmented PDF publication with structured,
machine-readable, citable law.

This repository holds the conversion pipeline: a parser that turns published
gazette PDFs into validated Akoma Ntoso 3.0 XML.

## Contents

| Path | Purpose |
| --- | --- |
| `scripts/akn-parser.py` | Command-line entry point |
| `scripts/akn_parser/` | Parser implementation |
| `data/` | Source gazette PDFs |
| `out/` | Generated Akoma Ntoso XML |
| `schemas/` | OASIS Akoma Ntoso 3.0 XSD, used for validation |
| `config/` | Per-document metadata overrides |
| `tests/` | Test suite |
| `docs/` | Documentation |

## Requirements

- Python 3.9 or later
- [PyMuPDF](https://pymupdf.readthedocs.io/) and [lxml](https://lxml.de/)
  (installed from `requirements.txt`)

## Installation

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

On macOS and Linux the interpreter is `.venv/bin/python`.

## Quick start

Convert every base Act in `data/v0s/` to English Akoma Ntoso:

```bash
.venv/Scripts/python scripts/akn-parser.py -t base_act -l eng
```

Output is written to `out/base_act/eng/`. Each document is validated against
the Akoma Ntoso 3.0 schema before it is written:

```
[3/3] tranfer_of_teachers.pdf
    pages          : 10-19 of 19
    redactions     : 483 foreign-language run(s)
    AKN 3.0 schema : valid
    eIds           : 415 (0 duplicate, 0 malformed)
    references     : 26 internal, 5 left external, 0 dangling
    other language : 11 run(s) kept and tagged
    -> out/base_act/eng/tranfer_of_teachers.xml
```

Convert a single file:

```bash
.venv/Scripts/python scripts/akn-parser.py --pdf "data/v0s/kan_eng/tranfer_of_teachers.pdf" -l eng
```

See [docs/cli.md](docs/cli.md) for the full command reference.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/cli.md](docs/cli.md) | Command-line reference |
| [docs/architecture.md](docs/architecture.md) | Pipeline stages and data flow |
| [docs/akn-mapping.md](docs/akn-mapping.md) | How gazette structure maps to Akoma Ntoso elements |
| [docs/identifiers.md](docs/identifiers.md) | `eId` construction and FRBR URIs |
| [docs/cross-references.md](docs/cross-references.md) | Citation detection and resolution |
| [docs/languages.md](docs/languages.md) | Bilingual extraction and text encoding |
| [docs/api.md](docs/api.md) | Using the parser as a Python library |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Error messages and diagnostics |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup and conventions |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## Development

```bash
.venv/Scripts/python -m pytest tests -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

English extraction is supported for base Acts and amending Acts.

Text in the other language is **preserved, not deleted**. Each run is kept in
a `<span>` whose `xml:lang` records both the language and whether its
codepoints have been converted out of a legacy font encoding
(`kn`, `kn-Latn-x-nudi`, `kn-x-misencoded`). The Act's title in the enacting
language is additionally carried as a Work-level `FRBRalias`. See
[docs/languages.md](docs/languages.md#text-in-the-other-language).

Converting legacy Nudi text to Unicode is supported through a pluggable
interface, but **no converter ships with the parser** — a mapping table that
has not been checked by a reader of Kannada would turn a visibly broken
document into an invisibly wrong one. See
[docs/languages.md](docs/languages.md#transliteration).

Kannada *extraction* is **not** supported. The parser detects the encoding
problems in the source PDFs and stops with a diagnostic rather than emitting
unreliable text; see [docs/languages.md](docs/languages.md#kannada-support).

Amending Acts are converted as standalone documents. Consolidating an
amendment into a base Act to produce a new expression is not implemented.
