"""Command-line entry point."""
from __future__ import annotations

import argparse
import glob
import os
import sys

from . import language
from .extract import FOREIGN_POLICIES, FOREIGN_TAG
from .pipeline import DEFAULT_OVERRIDES, DEFAULT_SCHEMA, REPO_ROOT, ActParser

#: Document type -> the directory under data/ that holds its PDFs.  Both
#: spellings of "amendments" are accepted because the repository has used the
#: misspelt one.
DOC_TYPE_DIRS = {
    "base_act": ("v0s",),
    "amendment": ("amendments", "ammendments"),
}

#: Language of the text to extract.  This is deliberately separate from the
#: source directory: data/v0s/kan_eng holds bilingual PDFs from which either
#: language can be extracted.
LANG_CHOICES = [language.ENGLISH, language.KANNADA]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="akn-parser",
        description="Convert legislative PDFs to Akoma Ntoso 3.0 XML.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  akn-parser.py -t base_act -l eng\n"
            "  akn-parser.py --pdf data/v0s/kan_eng/tranfer_of_teachers.pdf -l eng\n"
            "  akn-parser.py -t base_act -l eng --strict --keep-text\n"
        ),
    )
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "-t", "--type", dest="doc_type", choices=sorted(DOC_TYPE_DIRS),
        help="Process every PDF of this document type under data/.",
    )
    source.add_argument(
        "--pdf", help="Process a single PDF at this path.",
    )
    p.add_argument(
        "-l", "--lang", default=language.ENGLISH, choices=LANG_CHOICES,
        help="Language to extract. Text in any other language is redacted "
             "(default: %(default)s).",
    )
    p.add_argument(
        "-d", "--dir", dest="subdir",
        help="Only read PDFs from this subdirectory of the data folder "
             "(e.g. 'kan_eng'). Default: every subdirectory.",
    )
    p.add_argument(
        "-n", "--count", type=int, default=0,
        help="Process at most this many PDFs (0 = all).",
    )
    p.add_argument(
        "--foreign", default=FOREIGN_TAG, choices=list(FOREIGN_POLICIES),
        help="What to do with text in the other language: 'tag' keeps it and "
             "records its language and encoding in xml:lang, 'mark' replaces "
             "it with an <omissis/>, 'omit' drops it silently, 'keep' leaves "
             "it untagged (default: %(default)s).",
    )
    p.add_argument("--out", help="Output directory (default: out/<type>/<lang>).")
    p.add_argument("--schema", default=DEFAULT_SCHEMA,
                   help="Akoma Ntoso XSD to validate against.")
    p.add_argument("--overrides", default=DEFAULT_OVERRIDES,
                   help="JSON file of per-document metadata overrides.")
    p.add_argument("--no-validate", action="store_true",
                   help="Skip schema validation.")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero if any document fails a check.")
    p.add_argument("--keep-text", action="store_true",
                   help="Also write the normalised intermediate text.")
    p.add_argument("--quiet", action="store_true")
    return p


def collect_pdfs(doc_type: str, subdir: str | None) -> list:
    roots = []
    for name in DOC_TYPE_DIRS[doc_type]:
        base = os.path.join(REPO_ROOT, "data", name)
        if os.path.isdir(base):
            roots.append(base)
    if not roots:
        raise SystemExit(
            f"No data directory for type {doc_type!r}; expected one of: "
            + ", ".join(os.path.join("data", n) for n in DOC_TYPE_DIRS[doc_type])
        )

    pdfs = []
    for root in roots:
        pattern = os.path.join(root, subdir, "*.pdf") if subdir else os.path.join(
            root, "**", "*.pdf"
        )
        pdfs.extend(glob.glob(pattern, recursive=not subdir))
    if not pdfs:
        where = os.path.join("data", "*", subdir or "**")
        raise SystemExit(f"No PDF files found under {where}")
    return sorted(set(pdfs))


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.pdf:
        pdfs = [args.pdf]
        out_dir = args.out or os.path.join(REPO_ROOT, "out", "single", args.lang)
    else:
        pdfs = collect_pdfs(args.doc_type, args.subdir)
        out_dir = args.out or os.path.join(REPO_ROOT, "out", args.doc_type, args.lang)

    if args.count > 0:
        pdfs = pdfs[: args.count]
    os.makedirs(out_dir, exist_ok=True)

    parser = ActParser(
        target_lang=args.lang,
        foreign_policy=args.foreign,
        schema_path=args.schema,
        overrides_path=args.overrides,
        validate=not args.no_validate,
    )

    say = (lambda *a: None) if args.quiet else print
    say(f"Converting {len(pdfs)} PDF(s) to Akoma Ntoso [lang={args.lang}] -> {out_dir}\n")

    failures = 0
    for index, pdf_path in enumerate(pdfs, 1):
        basename = os.path.splitext(os.path.basename(pdf_path))[0]
        out_path = os.path.join(out_dir, f"{basename}.xml")
        say(f"[{index}/{len(pdfs)}] {os.path.basename(pdf_path)}")
        try:
            result = parser.parse(pdf_path)
        except Exception as exc:                     # noqa: BLE001 - reported
            failures += 1
            say(f"    FAILED: {type(exc).__name__}: {exc}")
            continue

        with open(out_path, "wb") as fh:
            fh.write(result.xml)
        if args.keep_text:
            with open(os.path.join(out_dir, f"{basename}.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(result.text)

        kept = [p.number + 1 for p in result.pages if p.kept]
        say(f"    pages          : {_ranges(kept)} of {len(result.pages)}")
        say(f"    redactions     : {result.redactions} foreign-language run(s)")
        say(result.report.summary())
        say(f"    -> {out_path}\n")
        if not result.report.ok:
            failures += 1

    if failures:
        say(f"{failures} of {len(pdfs)} document(s) reported problems.")
    else:
        say(f"All {len(pdfs)} document(s) converted and validated.")
    return 1 if (failures and args.strict) else 0


def _ranges(numbers: list) -> str:
    if not numbers:
        return "none"
    spans, start, prev = [], numbers[0], numbers[0]
    for n in numbers[1:]:
        if n != prev + 1:
            spans.append((start, prev))
            start = n
        prev = n
    spans.append((start, prev))
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in spans)


if __name__ == "__main__":
    sys.exit(main())
