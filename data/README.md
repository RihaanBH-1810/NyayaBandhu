# Source PDF corpus

`catalog.json` is the index for every source PDF. PDFs live at
`acts/<gazette-year>/ka-<four-digit-act-number>-<gazette-year>/<title-slug>__<variant>__<language>.pdf`.
Use the **published Karnataka Act number and year**, even if the short title uses
another year. Languages are `eng`, `kan`, or `kan-eng`. Variants distinguish a
full Gazette (`gazette`) from a partial extract (`excerpt`) or another edition.
An amending Act has its own Act ID and one PDF; `affected_acts` links it to each
principal Act it changes. Act 37 of 2024, for example, links to two Acts.

Admins can add a base Act or amendment in `/admin`. Provide the Act ID, title
slug, language, and for amendments the affected Act IDs. The server checks any
legible Act citation against the entered ID, detects duplicate bytes, stores the
PDF here, and adds a catalog record. It then tries to import the source into the
review workspace. A source needing OCR, XML, or identity review remains in the
corpus and can be selected again after correction.

The parser's `-t` option discovers files from this catalog. `-d` filters a
subtree such as `2020/ka-0053-2020`; `--pdf` accepts a direct path.

## Corpus processing check

Run `PYTHONPATH=scripts .venv/bin/python scripts/corpus_health.py`. It checks
every cataloged PDF, converts it to English Akoma Ntoso, verifies its Act
identity and title, then imports distinct Acts and extracts amendment proposals
in a temporary review store. It reports alternate source editions separately.
An absent principal Act is shown under `missing_targets`; this does not block
review against a principal Act that is present.

The Karnataka Municipal Corporations Act, 1976 (`ka-0014-1977`) is available
as `consolidated-through-act-0001-2022`. Its own front matter lists amendments
through Act 1 of 2022. This is an amended principal-text edition, not the
original 1977 Gazette or evidence of the text at every earlier effective date.
It supplies the second principal Act referenced by Act 37 of 2024; retrospective
application still requires the appropriate historical predecessor.

In `/admin`, choose **Catalog PDF** to convert and import an existing source
without preparing XML. **Open selected PDF** displays any source edition.
