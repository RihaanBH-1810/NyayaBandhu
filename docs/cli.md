# Command-line reference

`scripts/akn-parser.py` converts legislative PDFs to Akoma Ntoso 3.0 XML.

```
akn-parser [-h] (-t {amendment,base_act} | --pdf PDF) [-l {eng,kan}]
           [-d SUBDIR] [-n COUNT] [--foreign {tag,mark,omit,keep}]
           [--out OUT] [--schema SCHEMA] [--overrides OVERRIDES]
           [--no-validate] [--strict] [--keep-text] [--quiet]
```

Exactly one of `-t` or `--pdf` is required.

## Options

### Selecting input

| Option | Description |
| --- | --- |
| `-t`, `--type {base_act,amendment}` | Process every PDF of this document type. `base_act` reads `data/v0s/`; `amendment` reads `data/amendments/` or `data/ammendments/`, whichever exists. |
| `--pdf PATH` | Process a single PDF instead. |
| `-d`, `--dir SUBDIR` | Restrict `-t` to one subdirectory, e.g. `-d kan_eng`. Default: all subdirectories, searched recursively. |
| `-n`, `--count N` | Process at most `N` PDFs. `0` (default) means all. |

### Language

| Option | Description |
| --- | --- |
| `-l`, `--lang {eng,kan}` | Language to extract. Default `eng`. Text in any other language is handled according to `--foreign`. |
| `--foreign {tag,mark,omit,keep}` | How to treat text in the other language. Default `tag`. |

`--foreign` values:

| Value | Behaviour |
| --- | --- |
| `tag` | Keep the text in a `<span>` carrying an `xml:lang` tag that records its language and encoding. Nothing is discarded. |
| `mark` | Replace each run with an Akoma Ntoso `<omissis/>` marker, recording that text was omitted at that point. |
| `omit` | Remove the text silently. |
| `keep` | Leave the other language in place with no tag. Intended for diagnosing extraction, not for producing documents. |

See [languages.md](languages.md) for how spans are classified.

### Output

| Option | Description |
| --- | --- |
| `--out DIR` | Output directory. Default `out/<type>/<lang>/`, or `out/single/<lang>/` with `--pdf`. |
| `--keep-text` | Also write the normalised intermediate text as `<name>.txt` alongside the XML. Useful when a provision has come out in the wrong place. |

One XML file is written per input PDF, named after the source file.

### Validation

| Option | Description |
| --- | --- |
| `--schema PATH` | Akoma Ntoso XSD to validate against. Default `schemas/akomantoso30.xsd`. |
| `--no-validate` | Skip schema validation. Other checks still run. |
| `--strict` | Exit with status 1 if any document fails a check. Without it the exit status is 0 as long as every document was written. |

### Metadata

| Option | Description |
| --- | --- |
| `--overrides PATH` | JSON file of per-document metadata overrides. Default `config/documents.json`. See [identifiers.md](identifiers.md#metadata-overrides). |

### Other

| Option | Description |
| --- | --- |
| `--quiet` | Suppress per-document progress output. |
| `-h`, `--help` | Show usage and exit. |

## Output report

Each document produces a report:

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

| Line | Meaning |
| --- | --- |
| `pages` | Which pages of the PDF were identified as the requested language and used. |
| `redactions` | Number of runs of other-language text found. |
| `AKN 3.0 schema` | Result of XSD validation. |
| `eIds` | Total identifiers, with counts of duplicates and identifiers that do not conform to the naming convention. |
| `references` | Internal `<ref>` elements emitted; citations of other instruments deliberately left unlinked; `<ref>` elements whose target does not exist. |
| `unresolved` | Citations that could not be resolved, listed with the provision they appear in. Only shown when non-zero. |
| `other language` | Runs of another language kept and tagged with `xml:lang`. Only shown when non-zero. |
| `UNTAGGED script` | Letters of another script that reached the output without a tag. Should always be absent. |

`dangling` and `duplicate` should always be zero. A non-zero value is a defect;
see [troubleshooting.md](troubleshooting.md).

## Exit status

| Status | Meaning |
| --- | --- |
| `0` | All documents were written. With `--strict`, also that all checks passed. |
| `1` | With `--strict`, at least one document failed a check or could not be parsed. |

## Examples

Convert all base Acts, failing the run on any defect:

```bash
.venv/Scripts/python scripts/akn-parser.py -t base_act -l eng --strict
```

Convert only the bilingual sources, keeping intermediate text for inspection:

```bash
.venv/Scripts/python scripts/akn-parser.py -t base_act -l eng -d kan_eng --keep-text
```

Convert the first two amending Acts to a scratch directory:

```bash
.venv/Scripts/python scripts/akn-parser.py -t amendment -l eng -n 2 --out /tmp/akn
```

Inspect what a bilingual PDF looks like without redaction:

```bash
.venv/Scripts/python scripts/akn-parser.py --pdf "data/v0s/kan_eng/BBMP Act.pdf" -l eng --foreign keep --keep-text --no-validate
```

Produce a document that carries no unconverted Kannada at all:

```bash
.venv/Scripts/python scripts/akn-parser.py -t base_act -l eng --foreign mark
```
