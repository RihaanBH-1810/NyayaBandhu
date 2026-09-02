# Python API

Using the parser as a library rather than through the command line.

The package lives in `scripts/akn_parser/` and is not installed to site-packages,
so add `scripts/` to the import path:

```python
import sys
sys.path.insert(0, "scripts")

from akn_parser.pipeline import ActParser
```

## Quick use

```python
from akn_parser.pipeline import ActParser

parser = ActParser(target_lang="eng")
result = parser.parse("data/v0s/kan_eng/tranfer_of_teachers.pdf")

print(result.report.schema_valid)      # True
print(result.meta.work_uri)            # /akn/in-ka/act/2020-03-26/4
open("out.xml", "wb").write(result.xml)
```

---

## `akn_parser.pipeline`

### `ActParser(...)`

Converts one PDF into a validated Akoma Ntoso document.

```python
ActParser(
    target_lang="eng",
    foreign_policy="tag",
    schema_path=DEFAULT_SCHEMA,
    overrides_path=DEFAULT_OVERRIDES,
    validate=True,
    keywords=(),
)
```

| Parameter | Description |
| --- | --- |
| `target_lang` | `"eng"` or `"kan"` |
| `foreign_policy` | `"tag"` (default), `"mark"`, `"omit"` or `"keep"` |
| `schema_path` | XSD to validate against. Empty string disables schema validation. |
| `overrides_path` | JSON metadata overrides |
| `validate` | When `False`, the schema is not loaded |
| `keywords` | Default classification keywords, used when the overrides file supplies none |

**`parse(pdf_path) -> ParseResult`**

Raises `FileNotFoundError` if the path does not exist, `UnusableEncodingError`
if the requested language cannot be recovered, `DuplicateEId` if the parsed
hierarchy produces colliding identifiers, and `ValueError` if no page carries
the requested language.

### `ParseResult`

| Attribute | Type | Description |
| --- | --- | --- |
| `xml` | `bytes` | Serialised document, ready to write |
| `text` | `str` | Normalised intermediate text |
| `document` | `ActDocument` | The parsed tree |
| `meta` | `DocumentMeta` | FRBR metadata |
| `report` | `ValidationReport` | Check results |
| `pages` | `list[PageStats]` | Per-page extraction statistics |
| `redactions` | `int` | Runs of other-language text found |

### Module constants

| Name | Value |
| --- | --- |
| `REPO_ROOT` | Repository root, derived from the module path |
| `DEFAULT_SCHEMA` | `schemas/akomantoso30.xsd` |
| `DEFAULT_OVERRIDES` | `config/documents.json` |

---

## `akn_parser.extract`

### `TextExtractor(...)`

```python
TextExtractor(
    target_lang="eng",
    foreign_policy="tag",
    min_page_letters=200,
    min_page_ratio=0.55,
    detect_tables=True,
)
```

**`extract(pdf_path) -> ExtractionResult`**

```python
from akn_parser.extract import TextExtractor

result = TextExtractor(target_lang="eng").extract("act.pdf")
print(result.kept_pages)     # [9, 10, 11, …]
print(result.redactions)
```

### `ExtractionResult`

| Attribute | Type |
| --- | --- |
| `text` | `str` |
| `pages` | `list[PageStats]` |
| `redactions` | `int` |
| `kept_pages` | `list[int]` (property) |

### `PageStats`

| Attribute | Description |
| --- | --- |
| `number` | Zero-based page index |
| `target_letters` | Letters of the requested language |
| `foreign_letters` | Letters of other languages |
| `kept` | Whether the page was used |
| `reason` | Why it was skipped or re-admitted |
| `tables` | Tables detected on the page |
| `target_ratio` | `target_letters / (target + foreign)` (property) |

### Functions and constants

| Name | Description |
| --- | --- |
| `sanitise(text)` | Remove codepoints XML cannot carry |
| `misencoded_share(text, (low, high))` | Fraction of a script's text that came out in unrelated blocks |
| `encode_table(rows)`, `decode_table(line)` | Table sentinel encoding |
| `encode_foreign(text, lang, encoding, font_encoding)`, `decode_foreign(token)` | Other-language run encoding |
| `REDACTION_MARK` | `U+E000` |
| `TABLE_MARK` | `U+E001` |
| `FOREIGN_MARK_TOKEN` | `U+E002` |
| `FOREIGN_TAG`, `FOREIGN_MARK`, `FOREIGN_OMIT`, `FOREIGN_KEEP` | Policy constants |
| `UnusableEncodingError` | Raised when the requested language cannot be recovered |

---

## `akn_parser.language`

| Name | Description |
| --- | --- |
| `classify_span_detail(text, font)` | Returns `(language, encoding)` |
| `classify_span(text, font)` | Returns language only |
| `script_letter_counts(text)` | `{"eng": n, "kan": n}`, ignoring digits and punctuation |
| `is_unicode_kannada_font(font)` | Whether a font name is a Unicode Kannada family |
| `ENGLISH`, `KANNADA`, `NEUTRAL` | Language constants |
| `UNICODE`, `LEGACY`, `SUSPECT` | Encoding constants |

```python
from akn_parser import language

language.classify_span_detail("PÀ£ÁðlPÀ gÁdå", "Nudi01e")
# ('kan', 'legacy')
language.classify_span_detail("Karnataka State", "BookmanOldStyle")
# ('eng', 'unicode')
```

---

## `akn_parser.transliterate`

Legacy-encoding conversion. No converter ships with the parser; see
[languages.md](languages.md#transliteration).

| Name | Description |
| --- | --- |
| `register(lang, encoding, converter)` | Install a converter |
| `unregister(lang, encoding)` | Remove one |
| `available(lang, encoding)` | Whether one is installed |
| `convert(text, lang, encoding)` | Returns `(text, encoding)`; unchanged if no converter applies |
| `encoding_for_font(font)` | Name the legacy encoding a font implements |
| `bcp47(lang, encoding, legacy_encoding)` | The `xml:lang` tag for a run |
| `LEGACY_ENCODINGS`, `ISO639_1`, `DEFAULT_ENCODING` | Lookup tables |

```python
from akn_parser import language, transliterate

transliterate.bcp47(language.KANNADA, language.LEGACY, "nudi")
# 'kn-Latn-x-nudi'

transliterate.register(language.KANNADA, "nudi", my_converter)
transliterate.convert("PÀ£ÁðlPÀ", language.KANNADA, "nudi")
# ('ಕರ್ನಾಟಕ', 'unicode')
```

A converter must return Unicode text, or raise / return `None` if it cannot
convert its input. A partial conversion is never accepted: the original text
and its legacy tag are kept instead.

---

## `akn_parser.normalize`

### `TextNormalizer`

**`run(raw) -> str`** — visual lines to one logical line per provision.

Module-level patterns available for inspection or extension:
`STRUCTURAL_START`, `ALL_CAPS`, `ORPHAN_ENUMERATOR`, `ROMAN`.

---

## `akn_parser.structure`

### `Tokenizer`

**`tokenize(text) -> list[Token]`**

### `TreeBuilder`

**`build(tokens) -> ActDocument`**

### Data classes

**`Token`** — `kind`, `num`, `text`, `raw`, `rows`

**`Node`** — one provision.

| Attribute | Description |
| --- | --- |
| `kind` | `section`, `subsection`, `clause`, `proviso`, `hcontainer`, … |
| `num` | Bare enumerator, e.g. `7`, `a`, `iv` |
| `heading`, `subheading` | Heading text |
| `name` | `name` attribute, for `hcontainer` |
| `paragraphs` | Blocks before any children (`str` or `TableBlock`) |
| `wrap_paragraphs` | Blocks after children |
| `children` | Child `Node`s |
| `list_type` | `alpha`, `roman`, or empty |
| `eid` | Assigned in stage 5 |
| `walk()` | Depth-first iterator over this node and its descendants |

**`TableBlock`** — `rows`, `eid`

**`Schedule`** — `num`, `heading`, `note`, `container`, `eid`

**`ActDocument`** — `preface`, `long_title`, `recitals`, `enacting_formula`,
`body`, `schedules`, `conclusions`, and `walk()`

```python
from akn_parser.structure import Tokenizer, TreeBuilder

doc = TreeBuilder().build(Tokenizer().tokenize(text))
for node in doc.walk():
    if node.kind == "section":
        print(node.num, node.heading)
```

---

## `akn_parser.eids`

| Name | Description |
| --- | --- |
| `EIdAssigner().assign(document) -> dict` | Stamps `eId` on every node; returns `{eId: node}` |
| `element_ref(kind) -> str` | Element name to naming-convention abbreviation |
| `normalise_num(raw) -> str` | `<num>` text to identifier number part |
| `is_conformant(eid) -> bool` | Naming-convention syntax check |
| `ELEMENT_REF` | The abbreviation table |
| `EID_SYNTAX` | Compiled grammar |
| `DuplicateEId` | Raised on collision |

---

## `akn_parser.refs`

### `CitationResolver(eid_index, schedule_eids=())`

**`markup(text, context_eid="") -> list[Segment]`**

```python
from akn_parser.refs import CitationResolver

resolver = CitationResolver({"sec_7": None, "sec_7__subsec_2": None})
for seg in resolver.markup("under sub-section (2)", "sec_7__subsec_1"):
    print(repr(seg.kind), repr(seg.text), repr(seg.href))
# 'text' 'under ' ''
# 'ref'  'sub-section (2)' '#sec_7__subsec_2'
```

The index passed to the constructor is `{eId: node}`; only its keys are used,
so any mapping with the right keys will do.

| Attribute | Description |
| --- | --- |
| `warnings` | `list[RefWarning]` of unresolved citations |
| `internal` | Count of internal references emitted |
| `external` | Count of citations left as external |

**`Segment`** — `kind` (`"text"`, `"ref"`, `"omissis"`, `"foreign"`), `text`,
`href`, and for `foreign` also `lang`, `encoding`, `font_encoding`

**`RefWarning`** — `context`, `citation`, `reason`

Patterns available for extension: `CITATION_CHAIN`, `EXTERNAL_TAIL`,
`EXTERNAL_LEAD`, `SCHEDULE_REF`, `ORDINAL_PROVISO`.

---

## `akn_parser.meta`

### `MetadataExtractor(overrides_path="")`

**`build(document, source_pdf, language) -> DocumentMeta`**

### `DocumentMeta`

Fields are listed in [identifiers.md](identifiers.md#metadata-overrides).
Derived properties:

| Property | Example |
| --- | --- |
| `work_uri` | `/akn/in-ka/act/2020-03-26/4` |
| `expression_uri` | `/akn/in-ka/act/2020-03-26/4/eng@2020-03-27` |
| `manifestation_uri` | `/akn/in-ka/act/2020-03-26/4/eng@2020-03-27.xml` |
| `component_uri(level, name)` | `…/!main`, `…/!schedule_1` |

`JURISDICTIONS` maps a state name to its ISO 3166-2 code.

---

## `akn_parser.render`

| Name | Description |
| --- | --- |
| `AknRenderer(meta, resolver).render(document)` | Returns an `lxml` element |
| `serialise(root) -> bytes` | Indented XML with declaration |
| `AKN_NS` | The Akoma Ntoso 3.0 namespace URI |
| `NSMAP` | Namespace map for `lxml` |

---

## `akn_parser.validate`

### `Validator(schema_path="")`

**`check(root, target_lang, resolver=None) -> ValidationReport`**

### `ValidationReport`

| Attribute | Description |
| --- | --- |
| `schema_valid` | `True`, `False`, or `None` when not checked |
| `schema_errors` | `list[(line, message)]` |
| `duplicate_eids` | Identifiers appearing more than once |
| `malformed_eids` | Identifiers failing the naming-convention grammar |
| `dangling_refs` | `list[(href, text)]` whose target does not exist |
| `foreign_residue` | `{script: letter_count}` of *untagged* other-script text |
| `tagged_runs` | Count of elements carrying an `xml:lang` tag |
| `unresolved_citations` | `list[RefWarning]` |
| `counts` | `{"eids": n, "refs": n, "external": n}` |
| `ok` | `True` when nothing failed (property) |
| `summary()` | The text block printed by the CLI |

---

## `akn_parser.cli`

| Name | Description |
| --- | --- |
| `main(argv=None) -> int` | Entry point; returns the exit status |
| `build_parser()` | The `argparse.ArgumentParser` |
| `collect_pdfs(doc_type, subdir)` | Sorted list of PDF paths |
| `DOC_TYPE_DIRS` | Document type to data directory names |
| `LANG_CHOICES` | Accepted `--lang` values |

```python
from akn_parser.cli import main
raise SystemExit(main(["-t", "base_act", "-l", "eng", "--strict"]))
```

---

## Exceptions

| Exception | Module | Raised when |
| --- | --- | --- |
| `UnusableEncodingError` | `extract` | The requested language is legacy-encoded or misencoded |
| `DuplicateEId` | `eids` | Two elements would receive the same identifier |
| `ValueError` | `extract` | No page carries the requested language |
| `FileNotFoundError` | `extract` | The PDF path does not exist |

See [troubleshooting.md](troubleshooting.md).
