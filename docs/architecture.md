# Architecture

How the parser is put together. For the XML it produces, see
[akn-mapping.md](akn-mapping.md); for using it as a library, see
[api.md](api.md).

## Overview

Conversion is a linear pipeline of nine stages. Each stage has a single input
type and a single output type, and none of them reaches backwards.

```
PDF
 │
 ├─ 1. extract      TextExtractor      → text + page statistics
 ├─ 2. normalize    TextNormalizer     → one logical line per provision
 ├─ 3. tokenize     Tokenizer          → typed tokens
 ├─ 4. build        TreeBuilder        → ActDocument (tree)
 ├─ 5. identify     EIdAssigner        → eIds stamped on the tree
 ├─ 6. metadata     MetadataExtractor  → DocumentMeta
 ├─ 7. resolve      CitationResolver   ─┐
 ├─ 8. render       AknRenderer        ←┘ → lxml element tree
 └─ 9. validate     Validator          → ValidationReport
                                        → XML bytes
```

`ActParser.parse()` in `akn_parser/pipeline.py` runs the sequence:

```python
extraction = TextExtractor(...).extract(pdf_path)
text       = TextNormalizer().run(extraction.text)
tokens     = Tokenizer().tokenize(text)
document   = TreeBuilder().build(tokens)
eid_index  = EIdAssigner().assign(document)
meta       = self.metadata.build(document, pdf_path, self.target_lang)
resolver   = CitationResolver(eid_index, [s.eid for s in document.schedules])
root       = AknRenderer(meta, resolver).render(document)
report     = self.validator.check(root, self.target_lang, resolver)
```

## Ordering constraints

Two dependencies fix the order of stages that would otherwise be independent.

**Identifiers precede rendering.** The citation resolver needs the complete set
of `eId`s before it can decide whether a citation resolves to something that
exists. This is what makes it possible to guarantee that no `<ref>` points at a
missing target.

**The body is rendered before `<meta>`.** Defined terms are discovered while
walking section 2, and each needs a `TLCTerm` declaration in `<references>`.
`AknRenderer.render()` therefore builds `<body>` into a detached element first,
then writes `<meta>`, then assembles the document in schema order.

## Modules

| Module | Lines | Responsibility |
| --- | --- | --- |
| `language.py` | 122 | Classify a text span by script and encoding |
| `transliterate.py` | 135 | Legacy-encoding conversion interface and BCP-47 tagging |
| `extract.py` | 390 | PDF → single-language text, table detection, encoding checks |
| `normalize.py` | 239 | Visual lines → logical lines |
| `structure.py` | 513 | Tokenising and tree building |
| `eids.py` | 148 | Naming-convention identifiers |
| `refs.py` | 400 | Citation detection and resolution |
| `meta.py` | 188 | FRBR metadata |
| `render.py` | 429 | Tree → Akoma Ntoso XML |
| `validate.py` | 152 | Schema, identifier, reference and language checks |
| `pipeline.py` | 80 | Stage orchestration |
| `cli.py` | 179 | Argument parsing, file discovery, reporting |

Dependencies run one way: `cli → pipeline → {extract, normalize, structure,
eids, meta, refs, render, validate}`, with `language.py` and `extract.py` as
shared leaves. There are no cycles.

## Stage 1: Extraction

`akn_parser/extract.py`

Operates on **spans**, not pages, so a line mixing an English sentence with an
inline Kannada title still yields clean English.

For each page:

1. `page.find_tables()` locates tables. Rows are cleaned — empty rows dropped,
   and a row whose first cell is empty is treated as a continuation of the row
   above. The result is encoded as a single JSON line prefixed with a sentinel
   character, so that later line re-flow cannot scramble it.
2. `page.get_text("dict")` yields blocks → lines → spans. Blocks are placed in
   reading order, with a two-column split applied when the page has a clear
   gutter.
3. Lines whose bounding box centre falls inside a table are skipped. This is
   done per line, not per block, because a text block can begin inside a table
   and continue past it.
4. Each span is classified by `language.classify_span_detail()`, which returns
   both the language and whether its codepoints are genuine Unicode or a
   legacy font encoding. Spans in the target language and script-neutral spans
   (digits, punctuation) are kept. Other-language spans are, by default,
   preserved: adjacent spans of the same language and encoding are merged into
   one run and carried onward as a base64 token, opaque to the whitespace
   collapsing and line re-flow that follow.

Pages are then selected: a page is kept if it has at least 200 letters of the
target language and they are at least 55% of its letters. Gaps inside the
resulting run are re-admitted, so a table-heavy page in the middle of an Act is
not lost.

Finally `_check_encoding()` rejects text that cannot be trusted — see
[languages.md](languages.md#encoding-checks).

**Output:** a string containing prose, other-language tokens (`U+E002`),
redaction sentinels (`U+E000`) and table lines (`U+E001`).

## Stage 2: Normalisation

`akn_parser/normalize.py`

Seven passes, in order:

| Pass | Effect |
| --- | --- |
| `_clean` | Remove codepoints XML cannot carry; collapse redaction runs; normalise quotes, dashes and spaces |
| `_dehyphenate` | Rejoin words split by an end-of-line hyphen, when the next line starts lowercase |
| `_drop_furniture` | Remove page numbers, registration lines, digital-signature artefacts |
| `_stitch_orphans` | Attach a line consisting only of an enumerator to the line that follows it |
| `_reflow` | Join wrapped lines into one logical line per provision |
| `_merge_tables` | Join a table split across a page break |
| `_drop_empty_after_redaction` | Remove lines that contained nothing but other-language text |
| `_merge_foreign_runs` | Join other-language tokens that a line break had split |

`_reflow` is the substantive pass. A line begins a new logical line only when
it opens a recognised structural unit — a section number, `(1)`, `(a)`, `(i)`,
`Provided`, `Explanation`, `CHAPTER`, `SCHEDULE`, or an all-capitals heading.
Matching is case sensitive: `NOTIFICATION` is a heading, `notification,
appoint.` is the tail of a wrapped sentence.

`_continues_citation` suppresses that match when the enumerator belongs to a
citation rather than a new provision, which happens when a citation wraps
across a line break:

```
… nominated by the Government under clause (b) of sub-section
(1) of section 8 shall, subject to the pleasure of the Government, …
```

Read naively, that `(1)` opens a second subsection 1. A line is treated as a
continuation when its predecessor ends on a citation keyword, or when its
enumerator is followed by a word no provision opens with (`of`, `to`, `and`,
`or`, `read`).

## Stage 3: Tokenising

`akn_parser/structure.py`, class `Tokenizer`

Each logical line becomes a `Token(kind, num, text, raw)`. Recognition order
matters: roman `(i)` is tested before alphabetic `(a)`, so `(ii)` is never read
as a two-letter alphabetic marker.

| Kind | Matches |
| --- | --- |
| `table` | A table sentinel line |
| `chapter`, `part` | `CHAPTER IV`, `PART II` |
| `schedule` | `SCHEDULE`, `FIRST SCHEDULE` |
| `proviso` | `Provided that`, `Provided further that`, `Provided also that` |
| `explanation` | `Explanation.-`, `Explanation 2:` |
| `subsection` | `(1)`, `(2a)` |
| `roman` | `(i)`, `(iv)` |
| `alpha` | `(a)`, `(bb)` |
| `section` | `7.`, `12A.` |
| `heading` | An all-capitals line |
| `text` | Anything else |

A second pass, `_resolve_ambiguous`, settles `(i)`, `(v)` and `(x)` — the three
markers valid in both a letter list and a roman list — using the nearest
enumerators before and after. See
[akn-mapping.md](akn-mapping.md#ambiguous-enumerators).

`raw` preserves the untouched line. Front matter is emitted from `raw` so that
`clause (3) of Article 348` keeps its `(3)`, which the subsection matcher would
otherwise consume.

## Stage 4: Tree building

`akn_parser/structure.py`, class `TreeBuilder`

A state machine over a stack of open elements, producing an `ActDocument`.

Document phases:

1. **Front matter**, until a section token arrives after the enacting formula
   (or a chapter/part token arrives). Lines route to `long_title`, `recitals`,
   `enacting_formula` or `preface`.
2. **Body.** Placement rules below.
3. **Schedules**, entered on a `schedule` token.
4. **Conclusions**, entered on the signature block. This is a sticky flag:
   everything after it is closing matter.

Placement within the body:

| Token | Placement |
| --- | --- |
| `section` | Close down to body/chapter/part, then push. Heading split at `.-`; an inline `(1)` becomes a real subsection. |
| `subsection` | Close down to the section, then push. |
| `alpha`, `roman` | `_pop_to_list()` — see below. Element name taken from the parent. |
| `proviso`, `explanation` | Close down to the nearest section or subsection. |
| `table` | Added to the innermost node's block list, not its children. |
| `text` | Appended to the innermost node. |

`_pop_to_list()` distinguishes an item that **continues** a sequence from one
that **starts** one. A continuation becomes the sibling of its predecessor; a
list opener nests inside whatever is currently open. Without that distinction a
restarted `(a)` list nested three levels down would rejoin the outer `(a)` list
and produce duplicate identifiers.

Each `Node` carries `paragraphs` (blocks added before it had children) and
`wrap_paragraphs` (blocks added after). Stage 8 uses that split to choose
between `<content>`, `<intro>` and `<wrapUp>`.

## Stages 5–6: Identifiers and metadata

`akn_parser/eids.py` walks the tree composing identifiers; `akn_parser/meta.py`
reads the act number, assent date, publication date and title out of the
preface and builds FRBR URIs. Both are documented in
[identifiers.md](identifiers.md).

## Stages 7–8: References and rendering

`akn_parser/refs.py`, `akn_parser/render.py`

The renderer walks the tree. For each paragraph it calls
`resolver.markup(text, context_eid)`, which returns a list of segments:

```python
[Segment("text", "The categories falling under clauses "),
 Segment("ref", "(i)", "#sec_10__subsec_1__cl_i"),
 Segment("text", " to "),
 Segment("ref", "(iv)", "#sec_10__subsec_1__cl_iv"),
 Segment("text", " are eligible …")]
```

Segments are of four kinds: `text`, `ref`, `omissis`, and `foreign` — the
last carrying a run of another language together with its encoding, which the
renderer emits as a `<span xml:lang="…">` after offering it to any registered
transliterator.

The renderer turns those into `<p>` with `<ref>` and `<omissis>` children. The
`context_eid` is what allows a relative citation such as `sub-section (3)` to
resolve against the provision it appears in. See
[cross-references.md](cross-references.md).

## Stage 9: Validation

`akn_parser/validate.py`

| Check | Method |
| --- | --- |
| Schema validity | `lxml.etree.XMLSchema` against `schemas/akomantoso30.xsd` |
| Identifier uniqueness | Every `@eId` in the document |
| Identifier syntax | Regex for the naming-convention grammar |
| Reference integrity | Every `href` fragment resolves to an existing `eId` |
| Language residue | Letters of another script surviving into the output |
| Unresolved citations | Collected from the resolver |

The schema cannot check the last four: it accepts any string as an `eId`, and a
`<ref>` pointing at a non-existent target is schema-valid. Those checks are
written by hand.

## Determinism

The pipeline contains no randomness, no model inference, no network access and
no concurrency. Given the same PDF and the same library versions, output is
byte-identical; this is verified across varying `PYTHONHASHSEED` values.

The one clock-dependent value is `FRBRManifestation/FRBRdate@date`, which
records the date the file was generated. It can be pinned per document through
`config/documents.json`. See [identifiers.md](identifiers.md#metadata-overrides).

Output does depend on the PyMuPDF version, which governs text and table
extraction. Pin it in `requirements.txt` if byte-reproducible output across
machines is required.
