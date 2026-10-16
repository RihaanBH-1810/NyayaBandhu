"""Local, versioned review of generated English base Acts."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.templating import Jinja2Templates
from lxml import etree
from pydantic import BaseModel

from akn_parser.pipeline import DEFAULT_SCHEMA
from akn_parser.render import AKN_NS
from webui import akn_view

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
DATA = ROOT / "data"
STORE = Path(os.environ.get("NYAYA_REVIEW_DIR", str(ROOT / "review-data")))
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter(prefix="/review")
_lock = threading.RLock()
_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
Q = lambda tag: f"{{{AKN_NS}}}{tag}"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse(data: bytes):
    return etree.fromstring(data, parser=_XML_PARSER)


def _xml(root):
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def _source(path: str) -> Path:
    candidate = (OUT / path).resolve()
    if not candidate.is_relative_to((OUT / "base_act" / "eng").resolve()) or not candidate.is_file() or candidate.suffix != ".xml":
        raise HTTPException(404, "Only generated English base Acts can be reviewed")
    return candidate


def _folder(draft_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{20}", draft_id):
        raise HTTPException(404, "Unknown draft")
    folder = STORE / draft_id
    if not (folder / "state.json").is_file():
        raise HTTPException(404, "Unknown draft")
    return folder


def _state(folder: Path):
    return json.loads((folder / "state.json").read_text(encoding="utf-8"))


def _atomic(path: Path, data: bytes):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _save_state(folder, state):
    _atomic(folder / "state.json", json.dumps(state, indent=2).encode())


def _pdf_path(source: str):
    name = Path(source).stem
    matches = list(DATA.rglob(name + ".pdf"))
    return matches[0] if matches else None


def _report(root):
    metadata = akn_view.extract_metadata(root)
    check = akn_view.validate(root, DEFAULT_SCHEMA, metadata.get("language") or "eng")
    return {"ok": check.ok, "schema_valid": check.schema_valid,
            "schema_errors": check.schema_errors[:20],
            "duplicate_eids": check.duplicate_eids[:20],
            "malformed_eids": check.malformed_eids[:20],
            "dangling_refs": check.dangling_refs[:20],
            "foreign_residue": check.foreign_residue,
            "summary": check.summary()}


def _node(root, eid: str):
    found = root.xpath("//*[@eId=$eid]", eid=eid)
    if len(found) != 1:
        raise HTTPException(404, f"Provision {eid!r} not found")
    return found[0]


def _outline(root):
    return [{"eid": e.get("eId"), "num": e.findtext(Q("num")) or "",
             "heading": e.findtext(Q("heading")) or "", "tag": etree.QName(e).localname}
            for e in root.iter() if etree.QName(e).localname in {"section", "subsection", "clause", "proviso"} and e.get("eId")]


def _summary(folder, state):
    root = _parse((folder / f"revision-{state['revision']}.xml").read_bytes())
    return {**state, "outline": _outline(root), "validation": _report(root),
            "pdf": f"/review/api/drafts/{folder.name}/source.pdf" if state.get("pdf") else None}


class Start(BaseModel):
    path: str


class Change(BaseModel):
    revision: int
    eid: str
    payload: dict


class Approval(BaseModel):
    revision: int
    reviewer: str


@router.get("", name="review_page")
def page(request: Request, path: str):
    source = _source(path)
    return TEMPLATES.TemplateResponse(request, "review.html", {"path": path, "name": source.stem})


@router.post("/api/drafts")
def create(body: Start):
    source = _source(body.path)
    raw = source.read_bytes()
    draft_id = hashlib.sha256(body.path.encode() + b"\0" + raw).hexdigest()[:20]
    with _lock:
        folder = STORE / draft_id
        if not folder.exists():
            folder.mkdir(parents=True)
            _atomic(folder / "source.xml", raw)
            _atomic(folder / "revision-0.xml", raw)
            pdf = _pdf_path(body.path)
            state = {"path": body.path, "source_sha256": hashlib.sha256(raw).hexdigest(),
                     "pdf": str(pdf.relative_to(DATA)) if pdf else None,
                     "revision": 0, "status": "draft", "approval": None,
                     "history": [{"revision": 0, "time": _now(), "eid": None, "description": "Source snapshot"}]}
            _save_state(folder, state)
        return {"id": draft_id, **_summary(folder, _state(folder))}


@router.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str):
    folder = _folder(draft_id)
    return _summary(folder, _state(folder))


@router.get("/api/drafts/{draft_id}/source.pdf")
def source_pdf(draft_id: str):
    state = _state(_folder(draft_id))
    if not state.get("pdf"):
        raise HTTPException(404, "No matching source PDF")
    path = (DATA / state["pdf"]).resolve()
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise HTTPException(404, "Source PDF missing")
    return FileResponse(path, media_type="application/pdf")


@router.get("/api/drafts/{draft_id}/original.xml")
def original_xml(draft_id: str):
    return Response((_folder(draft_id) / "source.xml").read_bytes(), media_type="application/xml")


@router.get("/api/drafts/{draft_id}/provisions/{eid}")
def provision(draft_id: str, eid: str):
    folder = _folder(draft_id)
    state = _state(folder)
    original = _node(_parse((folder / "source.xml").read_bytes()), eid)
    current = _node(_parse((folder / f"revision-{state['revision']}.xml").read_bytes()), eid)
    from webui import review_editor
    editor = review_editor.prepare(current)
    return {"eid": eid, "revision": state["revision"], "editor": editor,
            "original_xml": etree.tostring(original, encoding="unicode", pretty_print=True),
            "draft_xml": etree.tostring(current, encoding="unicode", pretty_print=True),
            "original_html": akn_view._render_block(original),
            "draft_html": akn_view._render_block(current)}


def _change(draft_id: str, body: Change, persist: bool):
    folder = _folder(draft_id)
    with _lock:
        state = _state(folder)
        if body.revision != state["revision"]:
            raise HTTPException(409, "This draft changed in another tab. Reload before editing.")
        raw = (folder / f"revision-{state['revision']}.xml").read_bytes()
        root = _parse(raw)
        target = _node(root, body.eid)
        before = etree.tostring(target, encoding="unicode", pretty_print=True)
        from webui import review_editor
        try:
            description = review_editor.edit(root, target, body.payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        after_node = _node(root, body.eid) if root.xpath("//*[@eId=$eid]", eid=body.eid) else None
        after = etree.tostring(after_node, encoding="unicode", pretty_print=True) if after_node is not None else "(removed)"
        report = _report(root)
        if not report["ok"]:
            raise HTTPException(422, {"message": "XML validation failed", "validation": report})
        diff = "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile="before", tofile="after", lineterm=""))
        result = {"description": description, "diff": diff, "validation": report,
                  "html": akn_view._render_block(after_node) if after_node is not None else ""}
        if persist:
            next_revision = state["revision"] + 1
            _atomic(folder / f"revision-{next_revision}.xml", _xml(root))
            state["revision"] = next_revision
            state["status"] = "draft"
            state["approval"] = None
            state["history"].append({"revision": next_revision, "time": _now(), "eid": body.eid, "description": description, "diff": diff})
            _save_state(folder, state)
            result["revision"] = next_revision
        return result


@router.post("/api/drafts/{draft_id}/preview")
def preview(draft_id: str, body: Change):
    return _change(draft_id, body, False)


@router.post("/api/drafts/{draft_id}/revisions")
def save_revision(draft_id: str, body: Change):
    return _change(draft_id, body, True)


@router.get("/api/drafts/{draft_id}/validate")
def validate(draft_id: str):
    folder = _folder(draft_id)
    state = _state(folder)
    return _report(_parse((folder / f"revision-{state['revision']}.xml").read_bytes()))


@router.post("/api/drafts/{draft_id}/approve")
def approve(draft_id: str, body: Approval):
    folder = _folder(draft_id)
    with _lock:
        state = _state(folder)
        if body.revision != state["revision"]:
            raise HTTPException(409, "This draft changed in another tab. Reload before approval.")
        if not body.reviewer.strip():
            raise HTTPException(422, "Reviewer name is required")
        raw = (folder / f"revision-{state['revision']}.xml").read_bytes()
        report = _report(_parse(raw))
        if not report["ok"]:
            raise HTTPException(422, {"message": "Validation failed", "validation": report})
        state["approval"] = {"reviewer": body.reviewer.strip(), "time": _now(), "revision": state["revision"]}
        state["status"] = "approved"
        _atomic(folder / "approved.xml", raw)
        _save_state(folder, state)
        return {"approval": state["approval"], "validation": report}


@router.get("/api/drafts/{draft_id}/export")
def export(draft_id: str):
    folder = _folder(draft_id)
    state = _state(folder)
    if state["status"] != "approved" or not state["approval"] or state["approval"]["revision"] != state["revision"]:
        raise HTTPException(409, "Approve the current valid revision before export")
    return FileResponse(folder / "approved.xml", media_type="application/xml", filename=Path(state["path"]).stem + "-reviewed.xml")
