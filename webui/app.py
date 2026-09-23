"""FastAPI app for the AKN viewer. Run with ``webui/run.py`` (see docs/webui.md).

Two jobs: list what is already in ``out/`` and let a document be opened for
reading, and drive ``akn_parser`` over a source PDF on demand so a document
does not have to be converted from the command line first. Everything about
what a document *is* (structure, validity, metadata) comes from
``akn_view`` and, beneath that, ``akn_parser`` itself; this module is routing
and request handling only.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fastapi import FastAPI, Form, Request  # noqa: E402
from fastapi.responses import PlainTextResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from starlette.status import HTTP_303_SEE_OTHER  # noqa: E402

from akn_parser import language  # noqa: E402
from akn_parser.cli import DOC_TYPE_DIRS, collect_pdfs  # noqa: E402
from akn_parser.extract import FOREIGN_POLICIES, FOREIGN_TAG  # noqa: E402
from akn_parser.pipeline import ActParser, DEFAULT_OVERRIDES, DEFAULT_SCHEMA  # noqa: E402

from webui import akn_view  # noqa: E402

OUT_DIR = REPO_ROOT / "out"
DATA_DIR = REPO_ROOT / "data"

app = FastAPI(title="NyayaBandhu Viewer")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _list_documents() -> list[dict]:
    """Every ``.xml`` under ``out/``, newest first, with its path relative to it."""
    if not OUT_DIR.is_dir():
        return []
    docs = []
    for path in OUT_DIR.rglob("*.xml"):
        stat = path.stat()
        docs.append({
            "rel_path": path.relative_to(OUT_DIR).as_posix(),
            "name": path.stem,
            "mtime": stat.st_mtime,
            "converted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "size_kb": round(stat.st_size / 1024),
        })
    return sorted(docs, key=lambda d: d["mtime"], reverse=True)


def _list_source_pdfs() -> dict:
    """Source PDFs available for on-demand conversion, keyed by document type."""
    sources = {}
    for doc_type in DOC_TYPE_DIRS:
        try:
            pdfs = collect_pdfs(doc_type, None)
        except SystemExit:
            pdfs = []
        sources[doc_type] = [
            Path(p).relative_to(DATA_DIR).as_posix() for p in pdfs
        ]
    return sources


def _resolve_xml_path(rel_path: str) -> Path | None:
    """Resolve *rel_path* to a file under ``out/``, refusing anything outside it."""
    candidate = (OUT_DIR / rel_path).resolve()
    try:
        candidate.relative_to(OUT_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@app.get("/")
def index(request: Request, error: str | None = None):
    """The document list and the conversion form.

    *error* is set when another route redirects here after a failure, and is
    shown as a banner. A conversion that raises lands here with the
    exception's name and message, the same text the CLI prints after
    ``FAILED:``.
    """
    return templates.TemplateResponse(request, "index.html", {
        "documents": _list_documents(),
        "sources": _list_source_pdfs(),
        "lang_choices": [language.ENGLISH, language.KANNADA],
        "foreign_choices": list(FOREIGN_POLICIES),
        "default_foreign": FOREIGN_TAG,
        "error": error,
    })


@app.post("/convert")
def convert(
    pdf: str = Form(...),
    doc_type: str = Form(...),
    lang: str = Form(language.ENGLISH),
    foreign: str = Form(FOREIGN_TAG),
):
    """Convert one PDF under ``data/`` and open the result.

    Writes to ``out/<doc_type>/<lang>/<name>.xml``, the same place
    ``akn-parser.py -t`` would, so the CLI and the viewer never keep two
    copies of one document. The request blocks for the whole conversion,
    which is about half a minute for the BBMP Act; the form on the index page
    shows a progress note while it waits.
    """
    pdf_path = (DATA_DIR / pdf).resolve()
    try:
        pdf_path.relative_to(DATA_DIR.resolve())
    except ValueError:
        return RedirectResponse(f"/?error=Refusing a path outside data/: {pdf}",
                                 status_code=HTTP_303_SEE_OTHER)
    if not pdf_path.is_file():
        return RedirectResponse(f"/?error=No such file: {pdf}",
                                 status_code=HTTP_303_SEE_OTHER)

    parser = ActParser(
        target_lang=lang, foreign_policy=foreign,
        schema_path=DEFAULT_SCHEMA, overrides_path=DEFAULT_OVERRIDES,
    )
    try:
        result = parser.parse(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        return RedirectResponse(
            f"/?error={type(exc).__name__}: {exc}", status_code=HTTP_303_SEE_OTHER
        )

    out_dir = OUT_DIR / doc_type / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pdf_path.stem}.xml"
    out_path.write_bytes(result.xml)

    rel_path = out_path.relative_to(OUT_DIR).as_posix()
    return RedirectResponse(f"/view?path={rel_path}", status_code=HTTP_303_SEE_OTHER)


@app.get("/view")
def view(request: Request, path: str):
    """Render one document from ``out/``. *path* is relative to ``out/``.

    The report is computed fresh from the file on every request rather than
    stored at conversion time, so a document edited by hand, or produced by
    some other tool, is checked as it now stands.
    """
    xml_path = _resolve_xml_path(path)
    if xml_path is None:
        return RedirectResponse(f"/?error=No such document: {path}",
                                 status_code=HTTP_303_SEE_OTHER)

    root = akn_view.load(xml_path)
    metadata = akn_view.extract_metadata(root)
    report = akn_view.validate(
        root, DEFAULT_SCHEMA, metadata.get("language") or language.ENGLISH
    )

    return templates.TemplateResponse(request, "view.html", {
        "path": path,
        "name": xml_path.stem,
        "document_html": akn_view.render_document_html(root),
        "outline": akn_view.build_outline(root),
        "metadata": metadata,
        "report": report,
    })


@app.get("/raw")
def raw(path: str):
    """The file exactly as written, for the Raw XML pane.

    Fetched by the page after it loads rather than inlined into it. Inlined,
    the BBMP Act's XML would add close to a megabyte to every view of it.
    """
    xml_path = _resolve_xml_path(path)
    if xml_path is None:
        return PlainTextResponse("No such document.", status_code=404)
    return PlainTextResponse(
        xml_path.read_text(encoding="utf-8"), media_type="application/xml"
    )
