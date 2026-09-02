# Contributing

## Development setup

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

On macOS and Linux the interpreter is `.venv/bin/python`.

The parser is not installed as a package. Run it through
`scripts/akn-parser.py`, which puts `scripts/` on the import path; tests do the
same through `tests/conftest.py`.

## Tests

```bash
.venv/Scripts/python -m pytest tests -q
```

| File | Covers |
| --- | --- |
| `test_language.py` | Span classification by script and encoding |
| `test_transliterate.py` | Tagging, the converter hook, and run round-tripping |
| `test_encoding_guard.py` | Refusal to emit unrecoverable text |
| `test_structure.py` | Line re-flow, tokenising, hierarchy building |
| `test_eids.py` | Identifier construction and the naming-convention grammar |
| `test_refs.py` | Citation detection and resolution |
| `test_teachers_act.py` | End-to-end, against the Teachers Transfer Act |

The first five are unit tests with inline fixtures and run without any PDF.
`test_teachers_act.py` requires `data/v0s/kan_eng/tranfer_of_teachers.pdf` and
skips if it is absent.

`test_teachers_act.py` is the regression suite for the pipeline as a whole. It
asserts on page selection, schema validity, identifier uniqueness, reference
integrity, FRBR values, and specific provisions whose structure has been
verified against the gazette. Changes that alter output should be reflected
there deliberately, not by loosening assertions.

## Adding a document

1. Put the PDF under `data/v0s/<lang>/` for a base Act, or
   `data/ammendments/` for an amending Act.
2. Run the parser and read the report.
3. If metadata was not extracted correctly, add an entry to
   `config/documents.json` — see
   [docs/identifiers.md](docs/identifiers.md#metadata-overrides).
4. Read the output. The validator confirms the document is well-formed Akoma
   Ntoso; it cannot confirm that section 7 contains the text of section 7.

## Working on the parser

The pipeline is nine stages with one-way dependencies, described in
[docs/architecture.md](docs/architecture.md). Work out which stage a defect
belongs to before changing anything — `--keep-text` shows the boundary between
extraction and mapping.

### Conventions

- Patterns that encode a rule from the specification carry a comment naming the
  rule, not restating the regex.
- Comments explain why a rule exists, with the provision that motivated it
  where one does. `BBMP s.83(2)(b)(iii)` is more useful than "handle nested
  lists".
- Structural constants — element abbreviations, keyword tables, font families —
  live at module level, named and commented, not inline.
- The parser reports what it could not do rather than guessing. A citation that
  will not resolve is left as plain text and recorded in `warnings`; it is
  never linked to a best guess.
- Failures that would produce a plausible-looking wrong document raise, rather
  than degrade quietly. `DuplicateEId` and `UnusableEncodingError` both exist
  for this reason.

### Changing the Akoma Ntoso mapping

`schemas/akomantoso30.xsd` is the authority. Before changing the renderer,
check the content model:

```python
import re
schema = open("schemas/akomantoso30.xsd", encoding="utf-8").read()
match = re.search(r'<xsd:complexType name="hierarchy"', schema)
print(schema[match.start():match.start() + 1200])
```

Update [docs/akn-mapping.md](docs/akn-mapping.md) in the same change.

### Changing identifiers

Identifier syntax is fixed by the
[Akoma Ntoso Naming Convention](https://docs.oasis-open.org/legaldocml/akn-nc/v1.0/akn-nc-v1.0.html).
Changes to `ELEMENT_REF` or `normalise_num` change every identifier in every
document and break external references to them. Treat identifiers as a public
interface.

### Adding a language

Three things are needed, in order:

1. Span classification in `akn_parser/language.py` — the script's Unicode
   block, and any legacy font families.
2. An encoding-repair step ahead of the parser if the sources are not clean
   Unicode. See [docs/languages.md](docs/languages.md#kannada-support).
3. Structural patterns in `akn_parser/normalize.py` and
   `akn_parser/structure.py`. The current patterns match English keywords and
   Latin enumerators throughout.

Adding a **transliterator** is separate and smaller: implement the contract in
`akn_parser/transliterate.py` and register it. Every legacy run in every
document is then converted on the next run, and its `xml:lang` tag changes
from `kn-Latn-x-nudi` to `kn` automatically. Do not add a mapping table that
has not been checked by a reader of the script — a wrong table turns a visibly
broken document into an invisibly wrong one.

## Determinism

Output is byte-identical for the same input and library versions. Two things
maintain that:

- No randomness, model inference, network access or concurrency.
- Nothing derived from set iteration order reaches the output. Where a set is
  iterated, the result is sorted or the caller requires a unique match.

`FRBRManifestation/FRBRdate@date` is the one clock-dependent value; it can be
pinned per document through `config/documents.json`.

If you add a lookup that iterates a set, sort it.

## Documentation

Documentation lives in `docs/` and is grouped by what the reader is doing:

| Reader | Document |
| --- | --- |
| Running the tool | [docs/cli.md](docs/cli.md), [docs/troubleshooting.md](docs/troubleshooting.md) |
| Consuming the XML | [docs/akn-mapping.md](docs/akn-mapping.md), [docs/identifiers.md](docs/identifiers.md), [docs/cross-references.md](docs/cross-references.md) |
| Calling the library | [docs/api.md](docs/api.md) |
| Changing the parser | [docs/architecture.md](docs/architecture.md), [docs/languages.md](docs/languages.md) |

Reference documents describe the system as it is. Rationale for a change and
comparison with previous behaviour belong in [CHANGELOG.md](CHANGELOG.md).
