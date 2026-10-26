"""Trusted-local CMS API; service invariants are shared with the CLI.

No accounts, legal attestation or publication. Do not expose this local viewer
as an authenticated multi-tenant service.
"""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from akn_consolidator.common import Conflict, parse
from akn_consolidator.service import Consolidator
from webui import akn_view

ROOT = Path(__file__).resolve().parent.parent
router = APIRouter(prefix='/consolidation/api', tags=['Amendment consolidation'])
page_router = APIRouter()
templates = Jinja2Templates(directory=str(ROOT / 'webui' / 'templates'))


@page_router.get('/consolidation', include_in_schema=False)
def workspace(request: Request):
    return templates.TemplateResponse(request, 'consolidation.html', {})


@page_router.get('/consolidation/read/{expression_id}', include_in_schema=False)
def read_expression(request: Request, expression_id: str):
    expression = call('expression', expression_id)
    root = parse(call('expression_xml', expression_id))
    return templates.TemplateResponse(request, 'consolidation_read.html', {
        'expression': expression, 'metadata': akn_view.extract_metadata(root),
        'document_html': akn_view.render_document_html(root),
        'status': 'Stale' if expression['invalidated_at'] else 'Approved' if expression['approved_at'] else 'Draft',
    })


def service():
    return Consolidator(os.environ.get('NYAYA_CONSOLIDATION_DIR', str(ROOT / 'consolidation-data' / 'visual-workspace')))


def call(method, *args, **kwargs):
    try:
        return getattr(service(), method)(*args, **kwargs)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Mutation(Input):
    revision: int = Field(ge=0)
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class Source(Input):
    xml_path: str
    pdf_path: str
    kind: str
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    work_id: str | None = None
    revision: int | None = Field(default=None, ge=0)


def source_path(value, folder, suffix):
    candidate = (ROOT / folder / value).resolve()
    if not candidate.is_relative_to((ROOT / folder).resolve()) or candidate.suffix != suffix or not candidate.is_file():
        raise HTTPException(400, f'Choose an existing {suffix} under {folder}/')
    return candidate


@router.get('/works')
def works(): return call('works')


@router.get('/catalog')
def catalog():
    return {
        'base_xml': sorted(p.relative_to(ROOT / 'out').as_posix() for p in (ROOT / 'out/base_act/eng').glob('*.xml')),
        'amendment_xml': sorted(p.relative_to(ROOT / 'out').as_posix() for p in (ROOT / 'out/amendment/eng').glob('*.xml')),
        'pdf': sorted(p.relative_to(ROOT / 'data').as_posix() for p in (ROOT / 'data').rglob('*.pdf')),
    }


@router.post('/sources')
def import_source(body: Source):
    xml=source_path(body.xml_path,'out','.xml').read_bytes()
    pdf=source_path(body.pdf_path,'data','.pdf').read_bytes()
    return call('import_source',xml,pdf,body.kind,body.actor,body.reason,body.work_id,body.revision)


@router.get('/sources/{source_id}/{kind}')
def source(source_id: str, kind: str):
    return Response(call('source_artifact',source_id,kind),media_type='application/pdf' if kind=='pdf' else 'application/xml')


@router.post('/sources/{source_id}/extract')
def extract(source_id: str, body: Mutation): return call('extract',source_id,**body.model_dump())


class Review(Mutation):
    manifest_revision: int = Field(ge=1)
    body: dict


@router.post('/manifests/{manifest_id}/review')
def review(manifest_id: str, body: Review): return call('review',manifest_id,**body.model_dump())


class Preview(Input):
    parent_id: str
    effective_date: str


@router.post('/works/{work_id}/preview')
def preview(work_id: str, body: Preview): return call('preview',work_id,**body.model_dump())


class Apply(Mutation):
    parent_id: str
    effective_date: str
    preview_hash: str


@router.post('/works/{work_id}/apply')
def apply(work_id: str, body: Apply): return call('apply',work_id,**body.model_dump())


class Approval(Mutation):
    xml_hash: str


@router.post('/expressions/{expression_id}/approve')
def approve(expression_id: str, body: Approval): return call('approve',expression_id,**body.model_dump())


class Correction(Mutation):
    operations: list[dict]
    evidence: dict


@router.post('/expressions/{expression_id}/correct')
def correct(expression_id: str, body: Correction): return call('correct',expression_id,**body.model_dump())


class Inventory(Input):
    target: dict
    old: str
    whole_word: bool = False


@router.post('/expressions/{expression_id}/inventory')
def inventory(expression_id: str, body: Inventory): return call('inventory',expression_id,**body.model_dump())


class Inspect(Input):
    expression_id: str
    operation_id: str
    body: dict


@router.post('/manifests/{manifest_id}/inspect')
def inspect(manifest_id: str, body: Inspect):
    return call('inspect_instruction', manifest_id, body.expression_id, body.body, body.operation_id)


@router.get('/works/{work_id}/history')
def history(work_id: str): return call('history',work_id)


@router.get('/works/{work_id}/workspace')
def cms_workspace(work_id: str): return call('workspace',work_id)


@router.get('/works/{work_id}/lookup')
def lookup(work_id: str, as_of: str, known_at: str | None = None): return call('lookup',work_id,as_of,known_at)


@router.get('/expressions/{expression_id}/xml')
def xml(expression_id: str):
    return Response(call('expression_xml',expression_id),media_type='application/xml',headers={'X-Nyaya-Use':'inspection; see history for approval status'})


@router.get('/expressions/{expression_id}')
def expression(expression_id: str): return call('expression',expression_id)


@router.get('/expressions/{expression_id}/export')
def export(expression_id: str):
    return Response(call('export',expression_id),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="consolidation.zip"'})


@router.get('/diff')
def diff(left: str, right: str): return Response(call('diff',left,right),media_type='text/plain')
