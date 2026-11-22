"""Visual review and reader portal over the existing consolidation store."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import difflib
import html
import io
import json
from pathlib import Path
import tempfile

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from lxml import html as html_tree
import pymupdf

from akn_consolidator.common import (Conflict, Q, canonical_hash, digest, encode,
                                    iso_date, now, parse, serialise, tag, text, validate)
from akn_consolidator.engine import apply_one, locate
from akn_parser.pipeline import ActParser
from webui import akn_view, review_editor
from webui.consolidation import service, call, Input, Mutation, source_path

ROOT = Path(__file__).resolve().parent.parent
pages = APIRouter()
api = APIRouter(prefix='/workspace/api', tags=['Visual workspace'])
templates = Jinja2Templates(directory=str(ROOT / 'webui/templates'))


@pages.get('/', include_in_schema=False)
@pages.get('/library', include_in_schema=False)
@pages.get('/library/search', include_in_schema=False)
@pages.get('/library/acts/{work_id}', include_in_schema=False)
@pages.get('/admin', include_in_schema=False)
@pages.get('/admin/acts/{work_id}', include_in_schema=False)
@pages.get('/admin/acts/{work_id}/amendments/{manifest_id}', include_in_schema=False)
@pages.get('/admin/acts/{work_id}/edit/{expression_id}', include_in_schema=False)
def page(request: Request, work_id: str = '', manifest_id: str = '', expression_id: str = ''):
    return templates.TemplateResponse(request, 'workspace.html', {})


def guarded(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


def current_versions(view):
    return [e for e in view['expressions'] if e['approved_at'] and not e['invalidated_at']
            and e['effective_date'] <= date.today().isoformat()]


def work_summary(svc, view):
    base = next(s for s in view['sources'] if s['kind'] == 'base')
    meta = akn_view.extract_metadata(parse(svc.source_artifact(base['id'], 'xml')))
    versions = current_versions(view)
    latest = versions[-1] if versions else None
    return {**view['work'], 'title': meta.get('title') or view['work']['uri'],
            'year': view['work']['uri'].split('/')[-2][:4],
            'jurisdiction': view['work']['uri'].split('/')[2],
            'last_updated': latest['effective_date'] if latest else None,
            'amendment_count': sum(s['kind'] == 'amendment' for s in view['sources']),
            'version_count': len(view['expressions']), 'approved_count': len(versions),
            'latest': latest, 'base_source_id': base['id'],
            'recent_activity': bool(latest and datetime.fromisoformat(latest['approved_at']) > datetime.now(timezone.utc)-timedelta(days=14))}


@api.get('/works')
def catalogue(public: bool = False, archived: bool = False):
    svc = service()
    result = []
    for work in svc.works(archived=archived and not public):
        view = svc.workspace(work['id'], include_archived=archived and not public)
        row = work_summary(svc, view)
        if not public or row['latest']:
            result.append(row)
    return result


@api.get('/works/{work_id}')
def detail(work_id: str, public: bool = False):
    svc = service()
    view = guarded(svc.workspace, work_id)
    summary = work_summary(svc, view)
    if public and not summary['latest']:
        raise HTTPException(404, 'No approved version available')
    sources = []
    for source in view['sources']:
        meta = akn_view.extract_metadata(parse(svc.source_artifact(source['id'], 'xml')))
        sources.append({**source, 'title': meta.get('title') or source['kind'].title(),
                        'date': source['metadata']['publication_date']})
    archived_sources = []
    if not public:
        for source in view['archived_sources']:
            meta = akn_view.extract_metadata(parse(svc.source_artifact(source['id'], 'xml')))
            archived_sources.append({**source, 'title': meta.get('title') or 'Amendment'})
    with svc.store.transaction() as db:
        related = [dict(row) for row in db.execute('SELECT * FROM related_documents WHERE work_id=? ORDER BY document_date DESC', (work_id,))]
        issues = [] if public else [dict(row) for row in db.execute('SELECT * FROM reader_issues WHERE work_id=? ORDER BY id DESC', (work_id,))]
    if public:
        # Reader payloads contain no pending decisions or private audit notes.
        versions = current_versions(view)
        allowed_sources = {s['id'] for s in sources if s['kind'] == 'base'}
        for version in versions:
            state = svc.expression(version['id'])['body']
            mids = set(state.get('manifest_revisions', {}))
            allowed_sources.update(m['source_id'] for m in view['manifests'] if m['id'] in mids)
        sources = [s for s in sources if s['id'] in allowed_sources]
        return {'summary': summary, 'expressions': versions, 'sources': sources,
                'related': [{k: r[k] for k in ('id','title','kind','category','document_date')} for r in related]}
    return {**view, 'summary': summary, 'sources': sources, 'archived_sources': archived_sources,
            'related': related, 'issues': issues}


@api.delete('/works/{work_id}')
def delete_work(work_id: str, body: Mutation):
    return call('archive_work', work_id, **body.model_dump())


@api.post('/works/{work_id}/restore')
def restore_work(work_id: str, body: Mutation):
    return call('restore_work', work_id, **body.model_dump())


@api.delete('/works/{work_id}/amendments/{source_id}')
def delete_amendment(work_id: str, source_id: str, body: Mutation):
    return call('archive_amendment', work_id, source_id, **body.model_dump())


@api.post('/works/{work_id}/amendments/{source_id}/restore')
def restore_amendment(work_id: str, source_id: str, body: Mutation):
    return call('restore_amendment', work_id, source_id, **body.model_dump())


class Canvas(Input):
    expression_id: str
    manifest_revision: int
    body: dict


def scope_node(root, op):
    if not op.get('target'):
        return None
    node = locate(root, op['target'])
    return next((a for a in [node, *node.iterancestors()] if tag(a) in {'section','hcontainer'}), node)


def word_diff(left, right):
    a, b = left.split(), right.split()
    parts = [[], []]
    for kind, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        old, new = html.escape(' '.join(a[i:j])), html.escape(' '.join(b[k:l]))
        parts[0].append(f'<del>{old}</del>' if kind in {'delete','replace'} else old)
        parts[1].append(f'<ins>{new}</ins>' if kind in {'insert','replace'} else new)
    return [' '.join(x) for x in parts]


def highlight_comparison(before, after):
    """Mark changed paragraphs without flattening inline links or table cells."""
    trees = [html_tree.fragment_fromstring(raw or '<div></div>', create_parent='div')
             for raw in (before, after)]
    maps = [{n.get('data-eid'): n for n in tree.xpath('.//p[@data-eid]')}
            for tree in trees]
    for side, mapping in enumerate(maps):
        for eid, node in mapping.items():
            other = maps[1-side].get(eid)
            change = ('deleted' if side == 0 else 'inserted') if other is None else (
                'substituted' if ''.join(node.itertext()) != ''.join(other.itertext()) else None)
            if change:
                node.set('class', node.get('class', '') + ' wording-' + change)
    return [''.join(html_tree.tostring(n, encoding='unicode') for n in tree) if raw else ''
            for tree, raw in zip(trees, (before, after))]


def make_canvas(svc, manifest_id, request):
    with svc.store.transaction() as db:
        manifest = svc._manifest(db, manifest_id)
        expr = svc._expression(db, request.expression_id)
        if manifest['revision'] != request.manifest_revision:
            raise Conflict('Instruction review changed; reload the workbench')
        if expr['work_id'] != manifest['work_id'] or request.body.get('source_id') != manifest['source_id']:
            raise ValueError('Predecessor and amendment must belong to this Act')
        root = parse(svc.store.read(expr['xml_hash']))
        identities = dict(expr['body']['identities']); tombstones = list(expr['body']['tombstones'])
        rows = []; stopped = False
        provision_index = {}
        def index_provisions(tree):
            for node in tree.iter():
                if tag(node) in {'section','subsection','clause','subclause','proviso','hcontainer'} and node.get('eId'):
                    provision_index[node.get('eId')] = {'eid':node.get('eId'), 'label':akn_view.provision_label(node, context=True)}
        index_provisions(root)
        for op in request.body.get('operations', []):
            row = {'id': op['id'], 'action': op['action'], 'source': op['source'],
                   'status': op.get('review_decision') or op.get('review_status', 'pending')}
            if stopped:
                row['conflict'] = 'Resolve the preceding instruction to calculate this change.'
                rows.append(row); continue
            trial = deepcopy(root)
            try:
                before = scope_node(trial, op)
                row['label'] = (akn_view.provision_label(before, context=True)
                                if before is not None else op.get('classification', 'Separate legal effect'))
                row['before_html'] = akn_view._render_block(before) if before is not None else ''
                before_text = text(before) if before is not None else ''
                scope_eid = before.get('eId') if before is not None else None
                target = locate(trial, op['target']) if op.get('target') else None
                row['expected_hash'] = canonical_hash(target) if target is not None else None
                old_siblings = set(target.getparent()) if target is not None and target.getparent() is not None else set()
                ids, tombs = dict(identities), list(tombstones)
                result = apply_one(trial, op, ids, tombs, f"{manifest_id}:{manifest['revision']}:{op['id']}")
                if op['action'] == 'renumber' and before is target:
                    scope_eid = result['destination_eid']
                matches = trial.xpath('//*[@eId=$eid]', eid=scope_eid) if scope_eid else []
                after = matches[0] if matches else None
                if op['action'] == 'schedule_add':
                    after = [n for n in trial.iter(Q('hcontainer')) if n.get('name') == 'schedule'][-1]
                    row['before_html'] = ''; before_text = ''
                after_nodes = [after] if after is not None else []
                if op['action'] == 'insert_provision' and before is target and op.get('position', 'after') != 'last_child':
                    # A new sibling section lies outside the old section's subtree.
                    after_nodes = [n for n in target.getparent() if n is target or n not in old_siblings]
                row['after_html'] = ''.join(akn_view._render_block(n) for n in after_nodes)
                row['before_html'], row['after_html'] = highlight_comparison(row['before_html'], row['after_html'])
                row['before_diff'], row['after_diff'] = word_diff(before_text, ' '.join(text(n) for n in after_nodes))
                if op['action'] == 'effect':
                    row['effect'] = op.get('classification')
                row['changes'] = result
                # This is explicitly a proposal, including pending operations.
                root, identities, tombstones = trial, ids, tombs
                index_provisions(root)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                row['conflict'] = str(exc); stopped = True
            rows.append(row)
        return {'rows': rows, 'provisions':list(provision_index.values()), 'work_revision': svc._work(db, manifest['work_id'])['revision'],
                'manifest_revision': manifest['revision'], 'proposal': True}


@api.post('/manifests/{manifest_id}/canvas')
def canvas(manifest_id: str, body: Canvas):
    return guarded(make_canvas, service(), manifest_id, body)


def readable(svc, expression_id, public=False):
    expr = svc.expression(expression_id)
    if public and (not expr['approved_at'] or expr['invalidated_at'] or expr['effective_date'] > date.today().isoformat()):
        raise ValueError('Only current approved versions are available in the reader')
    root = parse(svc.expression_xml(expression_id))
    outline = [{'eid': n.get('eId'), 'tag': tag(n), 'label': akn_view.provision_label(n, context=True)}
               for n in root.iter() if tag(n) in review_editor.TYPES.keys() | review_editor.TEXT_ONLY and n.get('eId')]
    return expr, root, outline


@api.get('/expressions/{expression_id}/document')
def document(expression_id: str, public: bool = False):
    svc = service(); expr, root, outline = guarded(readable, svc, expression_id, public)
    return {'id': expr['id'], 'work_id': expr['work_id'], 'effective_date': expr['effective_date'],
            'xml_hash': expr['xml_hash'], 'approved_at': expr['approved_at'], 'invalidated_at': expr['invalidated_at'],
            'html': akn_view.render_document_html(root), 'outline': outline,
            'legal_effects': [{'classification':e.get('classification'),'effective_date':e.get('effectiveDate'),
                               'source':e.get('source'),'affected_work':e.get('affectedWork')}
                              for e in root.xpath('//*[local-name()="legalEffect"]')],
            'metadata': akn_view.extract_metadata(root)}


@api.get('/expressions/{expression_id}/citations')
def citations(expression_id: str, eid: str):
    svc = service()
    expr, root, _ = guarded(readable, svc, expression_id, False)
    if not root.xpath('//*[@eId=$eid]', eid=eid): raise HTTPException(404, 'Provision not found')
    with svc.store.transaction() as db:
        base = db.execute("SELECT * FROM sources WHERE work_id=? AND kind='base'",(expr['work_id'],)).fetchone()
        sources = {s['id']:s for s in db.execute('SELECT * FROM sources WHERE work_id=?',(expr['work_id'],))}
        original=parse(svc.store.read(base['xml_hash']))
        items = ([{'type':'base','label':'Base Act as published','source_id':base['id'],
                   'source_eid':eid,'pages':[],'date':json.loads(base['metadata'])['publication_date']}]
                 if original.xpath('//*[@eId=$eid]',eid=eid) else [])
        change_by_key = {c['operation']:c for c in expr['body'].get('changes',[])}
        for key in expr['body'].get('applied',[]):
            parts=key.split(':',2)
            if len(parts)!=3: continue
            mid,revision,opid=parts
            row=db.execute('SELECT * FROM manifests WHERE id=? AND revision=?',(mid,int(revision))).fetchone()
            if not row: continue
            manifest=json.loads(row['body']); op=next((o for o in manifest['operations'] if o['id']==opid),None)
            if not op or op['action']=='effect': continue
            change=change_by_key.get(key,{})
            target=change.get('target_eid') or op.get('target',{}).get('eid','')
            path=op.get('target',{}).get('path') or []
            if not target and path:
                prefixes={'section':'sec','subsection':'subsec','clause':'cl','subclause':'subcl','proviso':'proviso'}
                target='__'.join(prefixes.get(kind,kind)+'_'+str(number).strip('().') for kind,number in path)
            identity=expr['body'].get('identities',{}).get(eid,'')
            inserted=identity==digest((key+':'+eid).encode())[:24]
            occurrence=any((field:=hit.get('field','')) and (field==eid or field.startswith(eid+'__'))
                           for hit in op.get('occurrences',[]))
            if not (inserted or occurrence or target==eid or (target and eid.startswith(target+'__'))): continue
            source=sources.get(manifest['source_id'])
            if not source: continue
            meta=json.loads(source['metadata']); source_eid=op['source']['source_eid']
            title=akn_view.extract_metadata(parse(svc.store.read(source['xml_hash']))).get('title') or meta['work_uri']
            pages=op['source'].get('pdf_pages',[])
            label=f"{op['action'].replace('_',' ').capitalize()} by {source_eid} of {title}"
            if pages: label+=f", Gazette page {', '.join(map(str,pages))}"
            items.append({'type':op['action'],'label':label,'source_id':source['id'],
                          'source_eid':source_eid,'pages':pages,'date':op.get('effective_date') or manifest.get('effective_date')})
        for edit in expr['body'].get('visual_edits',[]):
            if edit['eid']==eid or eid.startswith(edit['eid']+'__'):
                ev=edit['evidence']; source=sources.get(ev['source_id'])
                if source:
                    items.append({'type':'editorial','label':'Editorial correction supported by source gazette',
                                  'source_id':source['id'],'source_eid':edit['eid'],
                                  'pages':ev['pdf_pages'],'date':expr['effective_date']})
    return {'expression_id':expression_id,'eid':eid,'citations':items}


@api.get('/works/{work_id}/coverage')
def reader_coverage(work_id: str, as_of: str):
    result = call('lookup', work_id, as_of)
    return result['coverage']


@api.get('/expressions/{expression_id}/xml')
def reader_xml(expression_id: str):
    svc = service(); guarded(readable, svc, expression_id, True)
    return Response(svc.expression_xml(expression_id), media_type='application/xml')


@api.get('/expressions/{expression_id}/pdf')
def reader_pdf(expression_id: str):
    svc = service(); expr, root, _ = guarded(readable, svc, expression_id, True)
    meta = akn_view.extract_metadata(root)
    content = '<h1>' + html.escape(meta.get('title') or 'Act') + '</h1><p>Local reviewed version · ' + expr['effective_date'] + '</p>' + akn_view.render_document_html(root)
    story = pymupdf.Story(content, user_css='body{font:11pt serif} .akn-label{font-weight:bold;margin-top:8pt} .akn-hanging .akn-label{float:left;margin-right:8pt} p{margin:4pt 0} table{border-collapse:collapse} td,th{border:1px solid #aaa;padding:3pt}')
    stream = io.BytesIO(); writer = pymupdf.DocumentWriter(stream)
    page = pymupdf.paper_rect('a4'); rect = page + (45,45,-45,-45)
    for _ in range(1500):
        device = writer.begin_page(page); more, _ = story.place(rect); story.draw(device); writer.end_page()
        if not more: break
    else: raise HTTPException(400, 'Document is too large to render')
    writer.close()
    return Response(stream.getvalue(), media_type='application/pdf', headers={'Content-Disposition':'attachment; filename="reviewed-act.pdf"'})


@api.get('/expressions/{expression_id}/provisions/{eid}')
def visual_provision(expression_id: str, eid: str):
    svc = service(); expr, root, _ = guarded(readable, svc, expression_id)
    node = guarded(locate, root, {'eid':eid})
    return {'editor': review_editor.prepare(node), 'html': akn_view._render_block(node),
            'xml_hash': expr['xml_hash'], 'revision': svc.workspace(expr['work_id'])['work']['revision'],
            'structural': expr['body']['kind'] == 'base' and tag(node) in review_editor.TYPES}


class VisualChange(Mutation):
    xml_hash: str
    eid: str
    payload: dict
    evidence: dict
    preview: bool = True


def edit_expression(svc, expression_id, request):
    svc._actor(request.actor, request.reason)
    with svc.store.transaction() as db:
        old = svc._expression(db, expression_id)
        svc._work(db, old['work_id'], request.revision)
        if old['invalidated_at'] or old['xml_hash'] != request.xml_hash:
            raise Conflict('This version changed or is stale; reopen the visual editor')
        if not old['approved_at'] and old['body']['kind'] == 'consolidated':
            raise Conflict('Approve the consolidated draft before making an editorial correction')
        if old['body']['kind'] != 'base' and request.payload.get('action') != 'text':
            raise ValueError('Structural amendments must be reviewed through the amendment workbench')
        ev = request.evidence
        source = db.execute('SELECT * FROM sources WHERE id=? AND work_id=?', (ev.get('source_id'), old['work_id'])).fetchone()
        if source is None or not isinstance(ev.get('quote'), str) or not ev['quote'].strip():
            raise ValueError('Choose a source and quote the wording supporting this correction')
        pages = ev.get('pdf_pages', [])
        maximum = json.loads(source['metadata'])['pdf_pages']
        if not pages or any(type(p) is not int or not 1 <= p <= maximum for p in pages):
            raise ValueError('Choose evidence pages within the source PDF')
        root = parse(svc.store.read(old['xml_hash']))
        before_xml = serialise(root).decode()
        nodes = {n: n.get('eId') for n in root.iter() if n.get('eId')}
        node = locate(root, {'eid': request.eid})
        before_html = akn_view._render_block(node)
        description = review_editor.edit(root, node, request.payload)
        report = validate(root)
        if not report['ok']: raise ValueError(report['summary'])
        if canonical_hash(root) == old['canonical_hash']: raise ValueError('No wording or structure changed')
        current = set(root.iter()); ids = {}; tombstones = list(old['body']['tombstones'])
        old_ids = old['body']['identities']
        for element, eid in nodes.items():
            if element in current:
                ids[element.get('eId')] = old_ids.get(eid) or digest((old['work_id'] + ':' + eid).encode())[:24]
            else: tombstones.append({'eid':eid, 'identity':old_ids.get(eid), 'operation':'visual_revision'})
        for element in current:
            eid = element.get('eId')
            if eid and eid not in ids: ids[eid] = digest((old['id'] + ':' + str(request.revision) + ':' + eid).encode())[:24]
        after_html = akn_view._render_block(node) if node in current else '<p>Provision removed.</p>'
        result = {'validation':report, 'description':description, 'before_html':before_html, 'after_html':after_html,
                  'diff':'\n'.join(difflib.unified_diff(before_xml.splitlines(), serialise(root).decode().splitlines(), fromfile='before',tofile='after'))}
        if request.preview: return result
        body = {**old['body'], 'kind':'base' if old['body']['kind']=='base' else 'editorial_correction',
                'supersedes':old['id'] if old['approved_at'] else old['body'].get('supersedes', old['id']),
                'evidence':ev, 'identities':ids, 'tombstones':tombstones, 'validation':report,
                'visual_edits':old['body'].get('visual_edits', []) + [{'eid':request.eid,'payload':request.payload,'evidence':ev,'description':description}]}
        parent_id = old['id'] if old['approved_at'] else old['parent_id']
        expression = svc._record_expression(db, old['work_id'], parent_id, old['effective_date'], root, body)
        # Replaced drafts are no longer approvable. Approved predecessors stay
        # current until the correction itself receives explicit approval.
        if not old['approved_at']: svc._invalidate(db, old['work_id'], [old['id']])
        svc.store.event(db, old['work_id'], 'visual_revision_saved', request.actor, request.reason,
                        {'expression_id':expression['id'],'previous_id':old['id'],'description':description})
        return {**result,'expression':expression,'revision':svc._bump(db,old['work_id'])}


@api.post('/expressions/{expression_id}/visual')
def visual_save(expression_id: str, body: VisualChange):
    return guarded(edit_expression, service(), expression_id, body)


@api.post('/upload')
async def upload(pdf: UploadFile = File(...), xml: UploadFile | None = File(None),
                 kind: str = Form(...), actor: str = Form(...), reason: str = Form(...),
                 work_id: str | None = Form(None), revision: int | None = Form(None)):
    pdf_bytes = await pdf.read(50_000_001)
    if len(pdf_bytes)>50_000_000: raise HTTPException(400,'PDF exceeds 50 MB')
    if xml and xml.filename:
        xml_bytes = await xml.read(10_000_001)
        if len(xml_bytes)>10_000_000: raise HTTPException(400,'XML exceeds 10 MB')
    else:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / Path(pdf.filename or 'gazette.pdf').name
            path.write_bytes(pdf_bytes)
            try:
                with pymupdf.open(stream=pdf_bytes, filetype='pdf') as doc:
                    if not doc.page_count: raise ValueError('Empty PDF')
            except Exception as exc:
                raise HTTPException(400, 'Cannot read source PDF') from exc
            result = await run_in_threadpool(guarded, ActParser().parse, str(path))
            xml_bytes = result.xml
    return await run_in_threadpool(call, 'import_source', xml_bytes,pdf_bytes,kind,actor,reason,work_id,revision)


class Related(Mutation):
    title: str
    kind: str
    category: str
    document_date: str
    pdf_path: str


@api.post('/works/{work_id}/related')
def add_related(work_id: str, body: Related):
    svc = service(); guarded(svc._actor,body.actor,body.reason)
    if body.kind not in {'Rules','Regulations','Notification'} or not body.title.strip() or not body.category.strip():
        raise HTTPException(400,'Enter a title, category, and document kind')
    guarded(iso_date,body.document_date)
    raw = source_path(body.pdf_path,'data','.pdf').read_bytes()
    try:
        with pymupdf.open(stream=raw,filetype='pdf') as doc:
            if not doc.page_count: raise ValueError('Empty PDF')
    except Exception as exc: raise HTTPException(400,'Invalid PDF') from exc
    with svc.store.transaction() as db:
        guarded(svc._work,db,work_id,body.revision)
        key = svc.store.put(raw); ident = digest(encode([work_id,key]))[:24]
        if db.execute('SELECT 1 FROM related_documents WHERE id=?',(ident,)).fetchone(): raise HTTPException(409,'This document is already linked')
        db.execute('INSERT INTO related_documents VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (ident,work_id,body.title.strip(),body.kind,body.category.strip(),body.document_date,key,now(),body.actor,body.reason))
        svc.store.event(db,work_id,'related_document_reviewed',body.actor,body.reason,{'id':ident,'title':body.title})
        return {'id':ident,'revision':svc._bump(db,work_id)}


@api.get('/related/{document_id}/pdf')
def related_pdf(document_id: str):
    svc = service()
    with svc.store.transaction() as db:
        row = db.execute('SELECT * FROM related_documents WHERE id=?',(document_id,)).fetchone()
        if row is None: raise HTTPException(404,'Document not found')
        return Response(svc.store.read(row['pdf_hash']),media_type='application/pdf')


class Issue(Input):
    expression_id: str
    message: str


@api.post('/works/{work_id}/issues')
def report_issue(work_id: str, body: Issue):
    svc=service(); expr, _, _=guarded(readable,svc,body.expression_id,True)
    if expr['work_id']!=work_id or not 10<=len(body.message.strip())<=5000:
        raise HTTPException(400,'Choose this Act and describe the issue in 10–5000 characters')
    with svc.store.transaction() as db:
        cursor=db.execute('INSERT INTO reader_issues(work_id,expression_id,message,created) VALUES(?,?,?,?)',
                          (work_id,body.expression_id,body.message.strip(),now()))
        return {'id':cursor.lastrowid}
