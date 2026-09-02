# Changelog

All notable changes to the parser are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Validation against the OASIS Akoma Ntoso 3.0 XSD, vendored at
  `schemas/akomantoso30.xsd`. Every document is validated before it is written.
- Checks the schema cannot perform: `eId` uniqueness and naming-convention
  syntax, reference integrity, and detection of text left in the wrong script.
- Test suite (93 tests) covering language classification and tagging,
  identifier construction, citation resolution, line re-flow and hierarchy
  building, plus end-to-end assertions against the Teachers Transfer Act.
- Table extraction. Schedules are emitted as `<table>`, including tables split
  across a page break.
- `<conclusions>`, `<longTitle>`, `<recitals>` and
  `<formula name="enactingFormula">` for front and back matter.
- Defined terms in a definitions section are wrapped in `<def>` and declared as
  `TLCTerm` in `<references>`.
- Encoding checks that stop conversion when the requested language cannot be
  recovered from the PDF, rather than emitting mojibake.
- Text in the other language is preserved and tagged with `xml:lang` rather
  than discarded. Tags distinguish clean Unicode (`kn`), legacy font encodings
  (`kn-Latn-x-nudi`) and text whose codepoints are demonstrably wrong
  (`kn-x-misencoded`), so a consumer can tell converted text from unconverted
  text without inspecting characters, and a converter can find every run that
  still needs work with one XPath.
- The Act's title in the enacting language is recovered from the notification
  and emitted as a Work-level `FRBRalias` carrying `xml:lang`.
- `akn_parser/transliterate.py`, a pluggable interface for converting legacy
  font encodings to Unicode. No converter is shipped; registering one converts
  every legacy run in every document and updates its tag automatically.
- `--foreign tag` (now the default) alongside `mark`, `omit` and `keep`.
- `config/documents.json` for per-document metadata overrides.
- CLI options `--foreign`, `--strict`, `--keep-text`, `--no-validate`,
  `--out`, `--schema`, `--overrides`, `--pdf`, `-d/--dir`.
- Per-document report showing pages used, redactions, schema result,
  identifier counts, reference counts and unresolved citations.
- Documentation set under `docs/`, plus `CONTRIBUTING.md`.

### Changed

- **Output is now schema-valid.** The previous output failed XSD validation.
  The principal cause was that hierarchical elements carried a `<content>`
  followed by child provisions; Akoma Ntoso permits either `<content>` or
  `intro?, children*, wrapUp?`, not both. Introductory text is now emitted as
  `<intro>`.
- **`eId` syntax now follows the naming convention.** Levels are separated by
  `__` and an element abbreviation from its number by `_`
  (`sec_7__subsec_1__cl_a`). The previous scheme used `-` for both
  (`sec_7-subsec_1-clause_a`), which is not a legal identifier, and used `__`
  as a de-duplication suffix, colliding with the level separator.
- **Identifier collisions now raise `DuplicateEId`** instead of being renamed
  with a numeric suffix. Identifiers are derived from tree position, so a
  collision indicates a mis-parsed hierarchy. This surfaced two hierarchy
  defects in the BBMP Act: a citation wrapping across a line read as a new
  subsection, and a restarted `(a)` list four levels deep rejoining the outer
  list.
- **`wId` is no longer emitted.** It was previously a copy of every `eId`. The
  naming convention specifies that the two are written separately only when
  they differ.
- **Provisos are `<proviso>`**, the Akoma Ntoso hierarchical element, rather
  than `<block name="proviso">`. They attach to the nearest enclosing section
  or subsection and are numbered within it.
- **Explanations are `<hcontainer name="explanation">`.** Akoma Ntoso has no
  `explanation` element.
- **Schedules are `<attachments><attachment><doc name="schedule">`** with their
  own FRBR identity, rather than `<components><component><schedule>`.
- **`<meta>` children are emitted in schema order.** `classification`
  previously followed `lifecycle`.
- **`eventRef/@type` is `generation`.** The previous value `publication` is not
  in the attribute's permitted set.
- **`<keyword>` carries the required `dictionary` attribute.**
- **FRBR metadata is derived from each document's own front matter** — act
  number, assent date, first-publication date, title — rather than being
  hard-coded. Every document previously carried the BBMP Act's identifiers.
- **FRBR URIs follow Naming Convention §4**: `/akn/in-ka/act/2020-03-26/4`,
  with an ISO 3166-2 jurisdiction code, the full date of the Work, and
  components introduced by `/!`.
- **Language separation operates on spans, using codepoints and font names.**
  The previous filter discarded non-ASCII characters, which removed Unicode
  Kannada while retaining legacy ASCII-mapped Kannada as though it were
  English.
- **Line re-flow is driven by the line that is starting.** A line begins a new
  logical line only when it opens a recognised structural unit. The previous
  rule joined a line to its predecessor unless the predecessor ended in
  punctuation, which split wrapped lines ending in a comma and joined provisos
  following a colon.
- **Citation resolution rewritten.** A `<ref>` is emitted only when its target
  exists. Chains such as `clause (i) to (iv) of sub-section (1) of section 10`
  are parsed as one citation; relative citations resolve against the provision
  they appear in; external citations are identified structurally from the
  instrument named beside them. The previous implementation matched the literal
  string `section N` and identified external citations by searching a
  200-character window for a hard-coded list of statute names, which produced
  both links from one Act's text to another Act's sections and `href` values
  pointing at identifiers that did not exist.
- Ambiguous enumerators `(i)`, `(v)` and `(x)` are resolved from surrounding
  enumerators rather than assumed to be roman.
- List items that restart a sequence nest, rather than rejoining the enclosing
  list of the same type.
- The parser is organised as a package under `scripts/akn_parser/`;
  `scripts/akn-parser.py` remains the entry point.

### Fixed

- `-t amendment` looked for `data/amendments/` while the directory is named
  `data/ammendments/`. Both spellings are now accepted.
- Codepoints that XML cannot carry are removed; previously they caused
  serialisation to fail on `BBMP-eng.pdf`.
- A text block beginning inside a table and continuing past it is no longer
  discarded whole; table filtering operates per line.

### Research notes

The approach to multilingual text follows established practice. AKN4UN,
Laws.Africa's Indigo and AKN4EU all model each language as a **separate
Expression of the same Work**, never as parallel text inside one document;
inline `xml:lang` is for incidental foreign text such as a quoted name, which
is exactly what a Kannada Act title inside an English notification is. Akoma
Ntoso does define a `mul` language code for genuinely mixed documents, but in
practice it is used for records that code-switch mid-stream, such as
parliamentary debates.

One difference matters here: Canada, Switzerland, Belgium, Hong Kong and the EU
apply the equal-authenticity rule, under which no language version is a
translation. India does not work that way for state legislation — Article
348(3) deems the English translation "the authoritative text thereof in the
English language". Which expression is the master for `wId` purposes is
therefore a legal question, and the documentation now says so rather than
assuming an answer.

### Known limitations

- Kannada extraction is not supported. See
  [docs/languages.md](docs/languages.md#kannada-support).
- Amending Acts are converted as standalone documents. Consolidation into a
  base Act is not implemented, and an amendment's citations into the base Act
  are reported as unresolved.
- Nine citations in the BBMP Act remain unresolved; they are external citations
  whose phrasing the external test does not recognise. None produces a wrong
  link.
- Schedules laid out as ruled tables become `<table>`. Where a schedule is
  really a numbered list, a hierarchy of provisions would carry more meaning.
