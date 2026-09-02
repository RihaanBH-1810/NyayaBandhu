# Troubleshooting

Diagnosing conversion failures and defects in the output.

## First step

Re-run with the intermediate text kept:

```bash
.venv/Scripts/python scripts/akn-parser.py --pdf path/to/file.pdf -l eng --keep-text
```

This writes `<name>.txt` next to the XML, containing the text after
normalisation and before tokenising — one line per provision. Most structural
problems are visible there, and it distinguishes an extraction fault from a
mapping fault:

- **Wrong text in the .txt** — the fault is in extraction or normalisation.
- **Right text, wrong XML** — the fault is in tokenising, tree building or
  rendering.

---

## Errors that stop conversion

### `UnusableEncodingError`

```
FAILED: UnusableEncodingError: tranfer_of_teachers.pdf: 14% of the Kannada
characters came out as unrelated codepoints (mostly General Punctuation) …
```

The requested language cannot be recovered from this PDF. Either the text is in
a legacy ASCII-mapped font, or the embedded font's `ToUnicode` map is wrong.

**Action:** use `--lang eng` if the document has an English translation. For
Kannada, the source needs an encoding-repair step first; see
[languages.md](languages.md#kannada-support). `--foreign keep --no-validate`
will let you inspect the raw bytes.

### `DuplicateEId`

```
FAILED: DuplicateEId: eId 'chp_III__sec_11__subsec_1' generated twice
(for <subsection> and <subsection>). This means the parsed hierarchy is wrong,
not that the identifier needs a suffix.
```

Two elements occupy what the parser believes is the same position in the tree.
Identifiers are derived from position, so a collision means the hierarchy is
mis-parsed — almost always because something was read as a new provision when
it was not.

**Action:** find the identifier in the `.txt` file. Common causes:

| Cause | Symptom in the text |
| --- | --- |
| A citation wrapped across a line break | A line beginning `(1) of section 8 shall …` |
| A restarted list at a deeper level | Two `(a)` items at what looks like the same level |
| A section number that is really a table cell or a year | A line beginning `1957. …` |

The first two are handled; a new instance means the pattern needs widening.
`_continues_citation` in `akn_parser/normalize.py` covers the first,
`_pop_to_list` in `akn_parser/structure.py` the second.

### `ValueError: No page of … carries enough 'eng' text`

No page met the selection thresholds.

**Action:** check `--lang`. If the document really is in the requested language,
the thresholds may be too strict for a short document — they are
`min_page_letters` and `min_page_ratio` on `TextExtractor`. A scanned PDF with
no text layer will also produce this; it needs OCR first.

### `FileNotFoundError`

The path given to `--pdf` does not exist. Note that `-t` expects PDFs under
`data/v0s/` or `data/amendments/`; use `--pdf` for files elsewhere.

---

## Defects reported in the output

### `AKN 3.0 schema : INVALID`

The document does not validate against `schemas/akomantoso30.xsd`. The first
ten errors are printed with line numbers. This is a bug in the renderer.

Common shapes:

| Message | Meaning |
| --- | --- |
| `element is not expected` | Wrong element order, or an element in a container that does not allow it |
| `Missing child element(s)` | A required child is absent — an empty `<body>`, for example |
| `is not a valid value of the local union type` | An attribute value outside its permitted set, or an empty date |
| `Duplicate key-sequence … eId-act` | Two identifiers collide within `<act>`, attachments included |

To reproduce outside the pipeline:

```python
from lxml import etree
schema = etree.XMLSchema(etree.parse("schemas/akomantoso30.xsd"))
doc = etree.parse("out/base_act/eng/name.xml")
schema.validate(doc)
for e in schema.error_log:
    print(e.line, e.message)
```

### `eIds : n (m duplicate, …)`

Should always be zero duplicates. A non-zero count here without a
`DuplicateEId` exception means duplicates were introduced by the renderer
rather than the identifier stage — an element given a hand-built `eId` that
collides.

### `eIds : n (…, m malformed)`

An identifier does not match the naming-convention grammar. Check it against
[identifiers.md](identifiers.md#eid-grammar); the usual cause is a `<num>`
containing characters that `normalise_num` does not reduce.

### `references : … n dangling`

A `<ref>` points at an identifier that does not exist. Should always be zero:
the resolver only emits a reference when the target is in the index, so a
dangling reference means a reference was constructed outside the resolver, or
the target's identifier changed after resolution.

### `unresolved : n citation(s)`

Citations left as plain text because they could not be resolved. This is not a
failure — the alternative is a wrong link — but a high count is worth
investigating. Reasons are listed in
[cross-references.md](cross-references.md#unresolved-citations).

Expected in normal operation:

- Citations of the Constitution and of central Acts whose phrasing the external
  test does not recognise.
- All citations in an amending Act, which point into the base Act.

### `foreign script : {'kan': n}`

Letters of another script survived into the output. With `--foreign keep` this
is expected. Otherwise it means span classification missed something — usually
a legacy Kannada font not in `_LEGACY_KANNADA_FONTS`.

**Action:** dump the fonts used in the document and check the list in
`akn_parser/language.py`:

```python
import pymupdf, collections
doc = pymupdf.open("file.pdf")
fonts = collections.Counter()
for page in doc:
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                fonts[span["font"]] += len(span["text"])
print(fonts.most_common(20))
```

---

## Structural problems that do not raise

These produce a valid document with the wrong shape. They are found by reading
the output, not by the validator.

### Provisions merged into one paragraph

Two provisions ended up in a single `<p>`. The second did not match
`STRUCTURAL_START` in `akn_parser/normalize.py`, or was suppressed by
`_continues_citation`.

### A sentence split across two provisions

A wrapped line was read as a new provision. Check whether it accidentally
matches `STRUCTURAL_START` — the usual culprit is a line beginning with a word
that is also a gazette keyword. Matching is case sensitive for this reason.

### A heading swallowed into the text, or text into the heading

Section headings are split at `.-`. A section whose text contains an early `.-`
sequence, or whose heading exceeds 20 words, will split in the wrong place. See
[akn-mapping.md](akn-mapping.md#section-headings).

### A list nested at the wrong depth

Element names come from the parent, so a mis-nested item takes the wrong
element. Check whether the item continues an existing sequence or opens a new
one — `_pop_to_list` in `akn_parser/structure.py` decides this from the
enumerator's value.

### Schedule rows scrambled or missing

Tables are detected by PyMuPDF. If a schedule is not laid out as a ruled table
it will not be detected and its rows will flow as prose. Check the `.txt` for a
line beginning with the table sentinel.

### Text from the wrong column

The two-column split is a heuristic that applies when a page has a clear
gutter. On a page with mixed layout it can interleave. `_reading_order` in
`akn_parser/extract.py`.

---

## Checking a document by hand

Count sections and confirm none are missing:

```python
from lxml import etree
NS = {"a": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}
tree = etree.parse("out/base_act/eng/name.xml")
nums = [s.find("{%s}num" % NS["a"]).text for s in tree.iter("{%s}section" % NS["a"])]
print(len(nums), nums[:5], nums[-5:])
```

List every reference and its target:

```python
for ref in tree.iter("{%s}ref" % NS["a"]):
    print(ref.get("href"), "|", "".join(ref.itertext()))
```

Extract the defined terms:

```python
for d in tree.iter("{%s}def" % NS["a"]):
    print(d.get("refersTo"), "".join(d.itertext()))
```

---

## Running the tests

```bash
.venv/Scripts/python -m pytest tests -q
```

A failure in `tests/test_teachers_act.py` indicates a regression against the
reference document. Failures in the unit test files point at the stage named by
the file — see [CONTRIBUTING.md](../CONTRIBUTING.md#tests).
