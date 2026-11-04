"""Download official Karnataka PDFs and assess parsing and instruction extraction.

This is an isolated diagnostic run. It never approves a legal text or writes to
the application's normal ``data/``, ``out/``, or review workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.request import Request, urlopen

import pymupdf
from lxml import etree

from akn_parser.pipeline import ActParser
from akn_consolidator.service import Consolidator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = Path(__file__).with_name("karnataka_corpus.json")
DEFAULT_WORKDIR = ROOT / "consolidation-data" / "karnataka-corpus-evaluation"


def words(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def fetch_pdf(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "NyayaBandhu corpus evaluation/1.0"})
    partial = destination.with_suffix(".partial")
    try:
        with urlopen(request, timeout=45) as response, partial.open("wb") as target:
            while block := response.read(1024 * 1024):
                target.write(block)
                if target.tell() > 50 * 1024 * 1024:
                    raise ValueError("PDF exceeds the 50 MB evaluation limit")
        with partial.open("rb") as downloaded:
            if downloaded.read(4) != b"%PDF":
                raise ValueError("Source did not return a PDF")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def evaluate(case: dict, workdir: Path, parser: ActParser, offline: bool) -> dict:
    source = workdir / "sources" / (case["id"] + ".pdf")
    source.parent.mkdir(parents=True, exist_ok=True)
    record = {"id": case["id"], "kind": case["kind"], "source": case["url"]}
    try:
        if not source.exists():
            if offline:
                raise FileNotFoundError(f"PDF not cached: {source}")
            fetch_pdf(case["url"], source)
        raw = source.read_bytes()
        if not raw.startswith(b"%PDF"):
            raise ValueError("Cached file is not a PDF")
        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            record["pdf_pages"] = pdf.page_count
            if not pdf.page_count:
                raise ValueError("PDF has no pages")
            if case.get("must_contain"):
                title = words(case["must_contain"])
                title_page = next((index + 1 for index in range(pdf.page_count)
                                   if title in words(pdf[index].get_text())), None)
                if title_page is None:
                    raise ValueError("PDF text does not match the expected Act title")
                record["title_page"] = title_page
        record["sha256"] = hashlib.sha256(raw).hexdigest()
        started = time.monotonic()
        result = parser.parse(str(source))
        record["parse_seconds"] = round(time.monotonic() - started, 2)
        record["validation"] = {
            "ok": result.report.ok,
            "schema_valid": result.report.schema_valid,
            "eids": result.report.counts.get("eids", 0),
            "duplicate_eids": result.report.duplicate_eids[:10],
            "malformed_eids": result.report.malformed_eids[:10],
            "dangling_refs": result.report.dangling_refs[:10],
            "schema_errors": result.report.schema_errors[:10],
            "unresolved_citations": len(result.report.unresolved_citations),
            "foreign_residue": result.report.foreign_residue,
        }
        record["kept_pages"] = [page.number + 1 for page in result.pages if page.kept]
        root = etree.fromstring(result.xml)
        record["sections"] = len(root.xpath("//*[local-name()='section']"))
        record["xml_bytes"] = len(result.xml)
        xml_path = workdir / "xml" / (case["id"] + ".xml")
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.write_bytes(result.xml)
        record["xml_path"] = str(xml_path)

        if case.get("base_xml") and result.report.ok:
            with tempfile.TemporaryDirectory(prefix="cms-smoke-", dir=workdir) as store_path:
                service = Consolidator(store_path)
                base = service.import_source(
                    (ROOT / case["base_xml"]).read_bytes(),
                    (ROOT / case["base_pdf"]).read_bytes(),
                    "base", "Corpus evaluation", "Check source import",
                )
                amendment = service.import_source(
                    result.xml, raw, "amendment", "Corpus evaluation",
                    "Check amendment import", base["work_id"], base["revision"],
                )
                extracted = service.extract(
                    amendment["source_id"], amendment["revision"],
                    "Corpus evaluation", "Check instruction extraction",
                )
                record["cms_smoke"] = {
                    "base_imported": True,
                    "amendment_imported": True,
                    "candidates": len(extracted["manifest"]["body"]["operations"]),
                }
        record["status"] = "parsed" if result.report.ok else "validation_failed"
    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    cli.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    cli.add_argument("--offline", action="store_true", help="Use cached PDFs only")
    args = cli.parse_args()
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.manifest.read_text(encoding="utf-8"))
    parser = ActParser(target_lang="eng")
    records = []
    for case in cases:
        record = evaluate(case, workdir, parser, args.offline)
        records.append(record)
        print(f"{record['id']}: {record['status']}")
        if record.get("error"):
            print(f"  {record['error']}")
        elif record.get("validation"):
            print(f"  {record['pdf_pages']} PDF pages, {record['sections']} sections, "
                  f"schema={record['validation']['schema_valid']}, "
                  f"{record['parse_seconds']}s")
    report = workdir / "report.json"
    report.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str) + "\n",
                      encoding="utf-8")
    print(f"Report: {report}")
    return 0 if all(r["status"] == "parsed" for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
