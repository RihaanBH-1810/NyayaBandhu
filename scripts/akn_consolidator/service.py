"""Transactional application services shared by CLI and FastAPI."""
from __future__ import annotations
from copy import deepcopy
import io
import json
import re
import zipfile
import pymupdf
from .common import Conflict, canonical_hash, digest, encode, iso_date, metadata, now, parse, serialise, validate
from .storage import Store
from .extraction import extract
from .engine import run, apply_one, seed_identities, update_metadata, locate, occurrences, public_hits, _references
from .common import Q, tag, text
from .identity import check as check_identity
from source_corpus import legacy_pdf


class Consolidator:
    def __init__(self, directory): self.store = Store(directory)

    @staticmethod
    def _actor(actor, reason):
        if not actor.strip() or not reason.strip(): raise ValueError('Actor and reason are required')

    @staticmethod
    def _work(db, work_id, revision=None, allow_archived=False):
        row = db.execute('SELECT * FROM works WHERE id=?',(work_id,)).fetchone()
        if row is None: raise ValueError('Work not found')
        if row['archived_at'] and not allow_archived: raise ValueError('Act is in Deleted Acts; restore it before editing')
        if revision is not None and row['revision'] != revision:
            raise Conflict(f"Stale work revision: expected {row['revision']}, received {revision}")
        return dict(row)

    @staticmethod
    def _bump(db, work_id):
        db.execute('UPDATE works SET revision=revision+1 WHERE id=?',(work_id,))
        return db.execute('SELECT revision FROM works WHERE id=?',(work_id,)).fetchone()[0]

    def _expression(self, db, expression_id):
        return self.store.load(db.execute('SELECT * FROM expressions WHERE id=?',(expression_id,)).fetchone())

    def _manifest(self, db, manifest_id):
        return self.store.load(db.execute('SELECT * FROM manifests WHERE id=? ORDER BY revision DESC LIMIT 1',(manifest_id,)).fetchone())

    def _manifests(self, db, work_id):
        return [self.store.load(r) for r in db.execute('SELECT m.* FROM manifests m JOIN sources s ON s.id=m.source_id WHERE m.work_id=? AND s.archived_at IS NULL AND m.revision=(SELECT MAX(revision) FROM manifests WHERE id=m.id) ORDER BY m.created,m.id',(work_id,))]

    def _record_expression(self, db, work_id, parent_id, effective_date, root, body):
        xml_hash = self.store.put(serialise(root)); manifest_hash = self.store.put(encode(body))
        expression_id = digest(encode([work_id,parent_id,effective_date,xml_hash,manifest_hash]))[:24]
        if db.execute('SELECT 1 FROM expressions WHERE id=?',(expression_id,)).fetchone():
            raise Conflict('This operation set has already been applied')
        db.execute('INSERT INTO expressions(id,work_id,parent_id,effective_date,xml_hash,canonical_hash,manifest_hash,body,created) VALUES(?,?,?,?,?,?,?,?,?)',
                   (expression_id,work_id,parent_id,effective_date,xml_hash,canonical_hash(root),manifest_hash,encode(body).decode(),now()))
        return self._expression(db, expression_id)

    def import_source(self, xml, pdf, kind, actor, reason, work_id=None, revision=None, identity_check_id=None):
        self._actor(actor,reason)
        if kind not in {'base','amendment'}: raise ValueError('Source kind must be base or amendment')
        root = parse(xml); meta = metadata(root)
        if not meta['work_uri'] or meta['language'] != 'eng': raise ValueError('English AKN Act identity is required')
        if not re.fullmatch(r'/akn/[a-z]{2}(?:-[a-z0-9]+)*/act/\d{4}-\d{2}-\d{2}/\d+',meta['work_uri']):
            raise ValueError('Expected a dated jurisdiction/act/number FRBR Work URI')
        if not pdf.startswith(b'%PDF'): raise ValueError('A source PDF is required')
        try:
            with pymupdf.open(stream=pdf,filetype='pdf') as document:
                if not document.page_count: raise ValueError('Source PDF has no pages')
                meta['pdf_pages']=document.page_count
        except Exception as exc:
            raise ValueError('Cannot read source PDF') from exc
        with self.store.transaction() as db:
            if kind == 'base':
                report = validate(root)
                if not report['ok']: raise ValueError('Base XML is invalid: '+report['summary'])
                work_id = digest(meta['work_uri'].encode())[:24]
                if db.execute('SELECT 1 FROM works WHERE id=?',(work_id,)).fetchone(): raise Conflict('Base work already exists')
                db.execute('INSERT INTO works(id,uri,revision) VALUES(?,?,?)',(work_id,meta['work_uri'],0))
            else:
                if revision is None: raise ValueError('Expected work revision is required')
                work=self._work(db,work_id,revision)
                if meta['work_uri']==work['uri']: raise Conflict('An amending instrument must have its own Work URI')
                if identity_check_id:
                    pending=db.execute('SELECT * FROM upload_checks WHERE id=? AND work_id=?',(identity_check_id,work_id)).fetchone()
                    if not pending or pending['status']!='confirmed' or pending['xml_hash']!=digest(xml) or pending['pdf_hash']!=digest(pdf):
                        raise Conflict('Identity review does not match these files')
                else:
                    base=db.execute("SELECT xml_hash FROM sources WHERE work_id=? AND kind='base'",(work_id,)).fetchone()
                    base_root=parse(self.store.read(base['xml_hash']))
                    title_node=base_root.find('./'+Q('act')+'/'+Q('longTitle'))
                    title=text(title_node) if title_node is not None else ''
                    finding=check_identity(root,pdf,work['uri'],title)
                    if finding['status']!='match':
                        check_id=digest(encode([work_id,digest(xml),digest(pdf)]))[:24]
                        self.store.put(xml); self.store.put(pdf)
                        db.execute('INSERT OR IGNORE INTO upload_checks(id,work_id,xml_hash,pdf_hash,status,result,actor,reason,created) VALUES(?,?,?,?,?,?,?,?,?)',
                                   (check_id,work_id,digest(xml),digest(pdf),finding['status'],encode(finding).decode(),actor,reason,now()))
                        return {'status':finding['status'],'check_id':check_id,'identity':finding,'revision':work['revision']}
                for row in db.execute("SELECT metadata FROM sources WHERE work_id=? AND kind='amendment'",(work_id,)):
                    if json.loads(row['metadata'])['work_uri']==meta['work_uri']:
                        raise Conflict('This amending instrument is already registered; review its existing instruction manifest')
            x,p = self.store.put(xml), self.store.put(pdf)
            source_id = digest(encode([work_id,kind,x,p]))[:24]
            if db.execute('SELECT 1 FROM sources WHERE id=?',(source_id,)).fetchone(): raise Conflict('Source already imported')
            db.execute('INSERT INTO sources(id,work_id,kind,xml_hash,pdf_hash,metadata,created) VALUES(?,?,?,?,?,?,?)',(source_id,work_id,kind,x,p,encode(meta).decode(),now()))
            if identity_check_id:
                db.execute('UPDATE upload_checks SET status=? WHERE id=?',('imported',identity_check_id))
            result = {'work_id':work_id,'source_id':source_id}
            if kind=='base':
                body={'kind':'base','source_id':source_id,'date_basis':'as_published; commencement not determined',
                      'identities':seed_identities(root,work_id),'tombstones':[],'applied':[], 'manifest_revisions':{}, 'validation':report}
                result['expression'] = self._record_expression(db,work_id,None,iso_date(meta['publication_date']),root,body)
            self.store.event(db,work_id,'source_imported',actor,reason,result)
            result['revision'] = self._bump(db,work_id)
            return result

    def upload_checks(self,work_id):
        with self.store.transaction() as db:
            self._work(db,work_id)
            return [dict(row) | {'result':json.loads(row['result'])} for row in db.execute(
                "SELECT * FROM upload_checks WHERE work_id=? AND status!='imported' ORDER BY created DESC",(work_id,))]

    def confirm_upload(self,check_id,revision,actor,reason,page,quote):
        self._actor(actor,reason)
        if not isinstance(page,int) or page<1 or not quote.strip(): raise ValueError('Gazette page and quotation are required')
        with self.store.transaction() as db:
            row=db.execute('SELECT * FROM upload_checks WHERE id=?',(check_id,)).fetchone()
            if not row or row['status']!='unclear': raise Conflict('Only an unclear identity can be confirmed')
            work=self._work(db,row['work_id'],revision)
            with pymupdf.open(stream=self.store.read(row['pdf_hash']),filetype='pdf') as doc:
                if page>len(doc): raise ValueError('Evidence page is outside the PDF')
            db.execute('UPDATE upload_checks SET status=?,resolved_at=?,resolved_by=?,resolution=? WHERE id=?',
                       ('confirmed',now(),actor,encode({'page':page,'quote':quote,'reason':reason,'work_uri':work['uri']}).decode(),check_id))
            return {'check_id':check_id,'status':'confirmed'}

    def complete_upload(self,check_id,revision,actor,reason):
        with self.store.transaction() as db:
            row=db.execute('SELECT * FROM upload_checks WHERE id=?',(check_id,)).fetchone()
            if not row or row['status']!='confirmed': raise Conflict('Confirm the amendment identity first')
            xml,pdf=self.store.read(row['xml_hash']),self.store.read(row['pdf_hash'])
            work_id=row['work_id']
        return self.import_source(xml,pdf,'amendment',actor,reason,work_id,revision,check_id)

    def prepare_teachers_sources(self,work_id,revision,actor,reason):
        """Register the pinned four-source set as pending proposals, never approvals."""
        from .teachers_candidates import BASE, SOURCES, checked, build_candidate_package
        self._actor(actor,reason)
        build_candidate_package()  # Check the complete source set before any write.
        with self.store.transaction() as db:
            work=self._work(db,work_id,revision)
            if work['uri']!=metadata(parse(checked(BASE[0])))['work_uri']:
                raise Conflict('Choose the bundled Teachers base Act')
            base=db.execute("SELECT * FROM sources WHERE work_id=? AND kind='base'",(work_id,)).fetchone()
            if not base or base['xml_hash']!=digest(checked(BASE[0])) or base['pdf_hash']!=digest(checked(BASE[1])):
                raise Conflict('The imported base source differs from the pinned Teachers source')
        registered=[]
        for name,stem,_day in SOURCES:
            xml=checked(f'out/amendment/eng/{stem}.xml')
            pdf=checked(str(legacy_pdf(stem).relative_to(__import__('pathlib').Path(__file__).resolve().parents[2])))
            uri=metadata(parse(xml))['work_uri']
            with self.store.transaction() as db:
                self._work(db,work_id)
                existing=next((dict(row) for row in db.execute(
                    "SELECT * FROM sources WHERE work_id=? AND kind='amendment'",(work_id,))
                    if json.loads(row['metadata'])['work_uri']==uri),None)
                current=self._work(db,work_id)['revision']
            if existing:
                if existing['archived_at'] or existing['xml_hash']!=digest(xml) or existing['pdf_hash']!=digest(pdf):
                    raise Conflict(f'Existing {name} source differs or is archived; resolve it before preparing drafts')
                source_id=existing['id']
            else:
                imported=self.import_source(xml,pdf,'amendment',actor,reason,work_id,current)
                if imported.get('status'): raise Conflict(f'{name} identity requires review')
                source_id=imported['source_id']
            with self.store.transaction() as db:
                manifest=db.execute('SELECT 1 FROM manifests WHERE source_id=?',(source_id,)).fetchone()
                current=self._work(db,work_id)['revision']
            if not manifest: self.extract(source_id,current,actor,reason)
            registered.append({'instrument':name,'source_id':source_id})
        with self.store.transaction() as db:
            return {'work_id':work_id,'revision':self._work(db,work_id)['revision'],
                    'status':'pending_legal_review','sources':registered}

    def extract(self, source_id, revision, actor, reason):
        self._actor(actor,reason)
        with self.store.transaction() as db:
            source=self.store.load(db.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone())
            if source['kind']!='amendment': raise ValueError('Choose an amendment source')
            if source['archived_at']: raise Conflict('Amendment is deleted; restore it before processing')
            work_id=source['work_id']; self._work(db,work_id,revision)
            manifest_id=digest((source_id+':instructions').encode())[:24]
            if db.execute('SELECT 1 FROM manifests WHERE id=?',(manifest_id,)).fetchone(): raise Conflict('Instructions already extracted; submit a review revision')
            body=extract(parse(self.store.read(source['xml_hash'])),self.store.read(source['pdf_hash']))
            body.update(source_id=source_id,sequence=len(self._manifests(db,work_id))+1)
            db.execute('INSERT INTO manifests VALUES(?,?,?,?,?,?,?,?)',(manifest_id,1,work_id,source_id,encode(body).decode(),now(),actor,reason))
            self.store.event(db,work_id,'instructions_extracted',actor,reason,{'manifest_id':manifest_id})
            return {'manifest':self._manifest(db,manifest_id),'revision':self._bump(db,work_id)}

    @staticmethod
    def _invalidate(db, work_id, expression_ids):
        ids=set(expression_ids)
        rows=list(db.execute('SELECT id,parent_id FROM expressions WHERE work_id=?',(work_id,)))
        while True:
            extra={r['id'] for r in rows if r['parent_id'] in ids}
            if extra <= ids: break
            ids |= extra
        stamp=now()
        for eid in ids:
            db.execute('UPDATE expressions SET invalidated_at=COALESCE(invalidated_at,?) WHERE id=?',(stamp,eid))
        return sorted(ids)

    def review(self, manifest_id, body, revision, manifest_revision, actor, reason):
        self._actor(actor,reason); body=deepcopy(body)
        with self.store.transaction() as db:
            previous=self._manifest(db,manifest_id);work=self._work(db,previous['work_id'],revision)
            if previous['revision']!=manifest_revision: raise Conflict('Stale instruction revision')
            old=previous['body']
            for key in ('format_version','source_id','source_work_uri','coverage'):
                if body.get(key)!=old.get(key): raise ValueError(f'Immutable manifest field: {key}')
            ops=body.get('operations',[]); old_ops={o['id']:o for o in old['operations']}
            if not isinstance(ops,list) or not ops or any(not isinstance(o,dict) or not isinstance(o.get('id'),str) for o in ops):
                raise ValueError('A nonempty list of identified operations is required')
            if len({o['id'] for o in ops})!=len(ops): raise ValueError('Operation IDs must be unique')
            if not set(old_ops)<= {o['id'] for o in ops}: raise ValueError('Instructions cannot be silently deleted; classify their effect')
            coverage={c['source_eid'] for c in body['coverage']}
            source=self.store.load(db.execute('SELECT * FROM sources WHERE id=?',(previous['source_id'],)).fetchone())
            if source['archived_at']: raise Conflict('Amendment is deleted; restore it before reviewing')
            max_page=source['metadata'].get('pdf_pages')
            if max_page is None:
                with pymupdf.open(stream=self.store.read(source['pdf_hash']),filetype='pdf') as document:
                    max_page=document.page_count
            for op in ops:
                if op.get('action') not in {'effect','blocked','text_replace','text_insert','text_omit','slot_edits','renumber',
                                          'insert_provision','replace_provision','omit_provision','schedule_add','table_insert'}:
                    raise ValueError('Unknown instruction action')
                if op.get('review_status') not in {'pending','accepted'}: raise ValueError('Unknown review status')
                if op['source']['source_eid'] not in coverage: raise ValueError('Operation lacks source coverage')
                if op['id'] in old_ops and op['source']!=old_ops[op['id']]['source']: raise ValueError('Original provenance is immutable')
                if op.get('review_status')=='accepted' and (not op['source'].get('pdf_pages') or not op['source'].get('quote')):
                    raise ValueError('Accepted operations require PDF page evidence and quotation')
                pages=op['source'].get('pdf_pages',[])
                if not isinstance(pages,list) or any(type(p) is not int or not 1<=p<=max_page for p in pages):
                    raise ValueError('Evidence page is outside the source PDF')
                if op['action']=='effect':
                    if op.get('classification') not in {'commencement','name_change','repeal_and_savings','ordinance_replacement','other'}:
                        raise ValueError('Choose a supported legal effect classification')
                    if op.get('review_status')=='accepted' and not op.get('details'):
                        raise ValueError('Accepted legal effect requires a summary')
                if op.get('effective_date'): iso_date(op['effective_date'])
                if op.get('review_status')=='accepted' and op['action'] not in {'effect','blocked'}:
                    if not isinstance(op.get('target'),dict): raise ValueError('Accepted edit requires a target')
                    if op['action'].startswith('text_') and (not op.get('old') or type(op.get('count')) is not int or op['count']<1):
                        raise ValueError('Accepted text edit requires a nonempty anchor and positive exact match count')
            expected=body.get('target_identity') or {}
            parts=work['uri'].split('/')
            matches=(expected.get('jurisdiction')==parts[2] and str(expected.get('number'))==parts[-1].lstrip('0') and expected.get('year')==parts[-2][:4])
            if body.get('identity_confirmed') and not matches: raise ValueError('Principal Act identity does not match the imported work')
            if not isinstance(body.get('sequence'),int) or body['sequence']<1: raise ValueError('Explicit positive amendment sequence is required')
            if body.get('effective_date'): iso_date(body['effective_date'])
            if body.get('date_confirmed') and (
                not isinstance(body.get('date_evidence'), str)
                or not body['date_evidence'].strip()
                or 'requires a recorded date determination' in body['date_evidence'].lower()
            ):
                raise ValueError('Record actual commencement evidence before confirming the date')
            ready=(body.get('identity_confirmed') and body.get('date_confirmed') and body.get('date_evidence')
                   and all(op.get('review_status')=='accepted' and op['action']!='blocked' and (op.get('effective_date') or body.get('effective_date')) for op in ops))
            body['status']='ready' if ready else 'needs_review'
            next_revision=previous['revision']+1
            db.execute('INSERT INTO manifests VALUES(?,?,?,?,?,?,?,?)',(manifest_id,next_revision,work['id'],previous['source_id'],encode(body).decode(),now(),actor,reason))
            affected=[]
            dates=[op.get('effective_date') or body.get('effective_date') for op in ops]
            first_date=min(d for d in dates if d) if any(dates) else None
            for row in db.execute('SELECT id,body FROM expressions WHERE work_id=?',(work['id'],)):
                state=json.loads(row['body'])
                if (manifest_id in state.get('manifest_revisions',{}) or
                    (ready and state.get('kind')!='base' and first_date and state.get('effective_date','')>=first_date)):
                    affected.append(row['id'])
            stale=self._invalidate(db,work['id'],affected)
            self.store.event(db,work['id'],'instructions_reviewed',actor,reason,{'manifest_id':manifest_id,'manifest_revision':next_revision,'stale':stale})
            return {'manifest':self._manifest(db,manifest_id),'revision':self._bump(db,work['id']),'stale':stale}

    def _preview(self, db, work_id, parent_id, effective_date):
        iso_date(effective_date);work=self._work(db,work_id)
        parent=self._expression(db,parent_id)
        if parent['work_id']!=work_id: raise ValueError('Parent belongs to another Act')
        if not parent['approved_at'] or parent['invalidated_at']: raise Conflict('Choose a current approved predecessor')
        if effective_date < parent['effective_date']: raise Conflict('Effective date precedes the selected predecessor; replay from an earlier expression')
        root=parse(self.store.read(parent['xml_hash'])); manifests=self._manifests(db,work_id)
        selected=[]; revisions=dict(parent['body']['manifest_revisions']); applied=list(parent['body']['applied']); applications=[]
        missing=[r['id'] for r in db.execute("SELECT s.id,s.metadata FROM sources s WHERE work_id=? AND kind='amendment' AND archived_at IS NULL AND NOT EXISTS(SELECT 1 FROM manifests m WHERE m.source_id=s.id)",(work_id,))
                 if not (json.loads(r['metadata']).get('publication_date') or '')>effective_date]
        if missing: raise Conflict('Extract all registered amendment sources first: '+', '.join(missing))
        ordering=set()
        for manifest in manifests:
            body=manifest['body']; mid=manifest['id']
            if mid in revisions and revisions[mid]!=manifest['revision']: raise Conflict('Predecessor uses an obsolete instruction revision')
            pending=[op for op in body['operations'] if f"{mid}:{manifest['revision']}:{op['id']}" not in applied]
            source=self.store.load(db.execute('SELECT * FROM sources WHERE id=?',(manifest['source_id'],)).fetchone())
            published=source['metadata'].get('publication_date')
            # An undated, later-published instrument cannot block an earlier
            # historical version. Once its publication date is reached, its
            # commencement and every instruction still need review.
            relevant=[op for op in pending if (
                (op.get('effective_date') or body.get('effective_date') or published or '')<=effective_date)]
            if relevant and body['status']!='ready':
                problems=[]
                if not body.get('identity_confirmed'): problems.append('principal Act identity unconfirmed')
                if not body.get('effective_date') and any(not op.get('effective_date') for op in relevant):
                    problems.append('commencement date unset')
                elif not body.get('date_confirmed'): problems.append('commencement evidence unconfirmed')
                count=sum(op.get('review_status')!='accepted' or op.get('action')=='blocked' for op in relevant)
                if count: problems.append(f'{count} instructions pending')
                raise Conflict('Unresolved amendment review for '+body['source_work_uri']+': '+', '.join(problems or ['review status unresolved']))
            for i,op in enumerate(pending):
                day=op.get('effective_date') or body.get('effective_date')
                if day is None or day>effective_date: continue
                if day<effective_date: raise Conflict(f'Apply the earlier effective-date batch {day} first')
                order=(day,body['sequence'],i)
                if order in ordering: raise Conflict('Same-date amendment sequence is ambiguous')
                ordering.add(order)
                key=f"{mid}:{manifest['revision']}:{op['id']}"
                selected.append((order,key,op));revisions[mid]=manifest['revision']
            if any(k.startswith(mid+':') for _,k,_ in selected): applications.append({'date':effective_date,'work_uri':body['source_work_uri']})
        if not selected: raise Conflict('No unapplied reviewed operations for this effective date')
        selected.sort(key=lambda x:x[0])
        root,result=run(root,[(k,o) for _,k,o in selected],parent['body']['identities'],parent['body']['tombstones'])
        if result['ok']:
            source_uris={m['id']:m['body']['source_work_uri'] for m in manifests}
            modifications=[{'operation':op,'change':change,'source_uri':source_uris[key.split(':')[0]]}
                           for (_,key,op),change in zip(selected,result['changes'])]
            update_metadata(root,effective_date,applications,modifications)
            for eid,identity in seed_identities(root,work_id).items():
                result['identities'].setdefault(eid,identity)
            result['validation']=validate(root);result['ok']=result['validation']['ok']
        result.update(work_id=work_id,parent_id=parent_id,effective_date=effective_date,work_revision=work['revision'],
                      applied=applied+[k for _,k,_ in selected],manifest_revisions=revisions)
        result['preview_hash']=digest(encode({'xml':canonical_hash(root),'parent':parent_id,'operations':selected,'revision':work['revision']}))
        return root,result

    def preview(self,work_id,parent_id,effective_date):
        with self.store.transaction() as db:
            _,result=self._preview(db,work_id,parent_id,effective_date);return result

    def apply(self,work_id,parent_id,effective_date,revision,preview_hash,actor,reason):
        self._actor(actor,reason)
        with self.store.transaction() as db:
            self._work(db,work_id,revision)
            root,result=self._preview(db,work_id,parent_id,effective_date)
            if result['preview_hash']!=preview_hash: raise Conflict('Preview is obsolete; review a fresh preview')
            if not result['ok']: raise Conflict('Application blocked: '+json.dumps(result['conflicts'] or result['validation']))
            if db.execute('SELECT 1 FROM expressions WHERE parent_id=? AND effective_date=? AND canonical_hash=? AND invalidated_at IS NULL',
                          (parent_id,effective_date,canonical_hash(root))).fetchone():
                raise Conflict('This operation set has already been applied')
            expression=self._record_expression(db,work_id,parent_id,effective_date,root,{'kind':'consolidated',**result})
            self.store.event(db,work_id,'applied_draft',actor,reason,{'expression_id':expression['id'],'preview_hash':preview_hash})
            return {'expression':expression,'revision':self._bump(db,work_id)}

    def correct(self, expression_id, operations, evidence, revision, actor, reason):
        self._actor(actor,reason)
        if not operations: raise ValueError('Correction requires at least one operation')
        if not evidence.get('source_id') or not evidence.get('pdf_pages') or not evidence.get('quote'):
            raise ValueError('Correction requires source ID, PDF pages and quotation')
        with self.store.transaction() as db:
            parent=self._expression(db,expression_id); self._work(db,parent['work_id'],revision)
            if not parent['approved_at'] or parent['invalidated_at']: raise Conflict('Correction requires a current approved expression')
            source=db.execute('SELECT * FROM sources WHERE id=? AND work_id=?',(evidence['source_id'],parent['work_id'])).fetchone()
            if source is None or source['archived_at']: raise ValueError('Correction evidence must belong to an active source in this work')
            if any(op['action'] not in {'text_replace','slot_edits'} or not op.get('expected_hash') for op in operations):
                raise ValueError('Editorial corrections require text operations and expected target hashes')
            root,result=run(parse(self.store.read(parent['xml_hash'])),[(f'correction:{i}',op) for i,op in enumerate(operations)],parent['body']['identities'],parent['body']['tombstones'])
            if not result['ok']: raise Conflict('Correction blocked: '+json.dumps(result))
            if canonical_hash(root)==parent['canonical_hash']: raise ValueError('Correction makes no XML change')
            body={**parent['body'],**result,'kind':'editorial_correction','supersedes':expression_id,'evidence':evidence,'corrections':operations}
            expression=self._record_expression(db,parent['work_id'],expression_id,parent['effective_date'],root,body)
            self.store.event(db,parent['work_id'],'correction_drafted',actor,reason,{'expression_id':expression['id']})
            return {'expression':expression,'revision':self._bump(db,parent['work_id'])}

    def approve(self,expression_id,revision,xml_hash,actor,reason):
        self._actor(actor,reason)
        with self.store.transaction() as db:
            expression=self._expression(db,expression_id);work_id=expression['work_id'];self._work(db,work_id,revision)
            if expression['approved_at'] or expression['invalidated_at']: raise Conflict('Expression is already approved or stale')
            if xml_hash!=expression['xml_hash']: raise Conflict('Approval must name the exact XML hash')
            if expression['parent_id']:
                parent=self._expression(db,expression['parent_id'])
                if not parent['approved_at'] or parent['invalidated_at']: raise Conflict('Predecessor is not current and approved')
            for mid,mrev in expression['body']['manifest_revisions'].items():
                if self._manifest(db,mid)['revision']!=mrev: raise Conflict('Instructions changed after application')
            if expression['body']['kind']=='consolidated':
                replay,report=self._preview(db,work_id,expression['parent_id'],expression['effective_date'])
                if not report['ok'] or canonical_hash(replay)!=expression['canonical_hash'] or report['applied']!=expression['body']['applied']:
                    raise Conflict('Instruction coverage changed after application; preview and apply again')
            if not validate(parse(self.store.read(xml_hash)))['ok']: raise Conflict('XML validation failed')
            if expression['body'].get('supersedes'):
                stale=self._invalidate(db,work_id,[expression['body']['supersedes']])
                db.execute('UPDATE expressions SET invalidated_at=NULL WHERE id=?',(expression_id,))
            else: stale=[]
            db.execute('UPDATE expressions SET approved_at=?,approved_by=? WHERE id=?',(now(),actor,expression_id))
            self.store.event(db,work_id,'approved',actor,reason,{'expression_id':expression_id,'xml_hash':xml_hash,'stale':stale})
            return {'expression':self._expression(db,expression_id),'revision':self._bump(db,work_id)}

    def history(self,work_id):
        with self.store.transaction() as db:
            return {'work':self._work(db,work_id),
                    'sources':[self.store.load(r) for r in db.execute('SELECT * FROM sources WHERE work_id=? ORDER BY created',(work_id,))],
                    'manifests':self._manifests(db,work_id),
                    'expressions':[self.store.load(r) for r in db.execute('SELECT * FROM expressions WHERE work_id=? ORDER BY effective_date,created',(work_id,))],
                    'events':[self.store.load(r) for r in db.execute('SELECT * FROM events WHERE work_id=? ORDER BY id',(work_id,))]}

    def workspace(self, work_id, include_archived=False):
        """Compact CMS read model; avoid sending XML-sized diffs and identity maps."""
        with self.store.transaction() as db:
            work = self._work(db, work_id, allow_archived=include_archived)
            expressions = []
            for row in db.execute('SELECT * FROM expressions WHERE work_id=? ORDER BY effective_date,created', (work_id,)):
                state = self.store.load(row)
                body = state['body']
                expressions.append({key: state[key] for key in (
                    'id','parent_id','effective_date','xml_hash','canonical_hash',
                    'created','approved_at','approved_by','invalidated_at')}
                                   | {'kind': body['kind'], 'validation': body.get('validation'),
                                      'editorial': bool(body.get('visual_edits') or body.get('corrections')),
                                      'supersedes': body.get('supersedes'),
                                      'applied_count': len(body.get('applied', [])),
                                      'change_count': len(body.get('changes', []))})
            return {
                'work': work,
                'sources': [self.store.load(row) for row in db.execute('SELECT * FROM sources WHERE work_id=? AND archived_at IS NULL ORDER BY created', (work_id,))],
                'archived_sources': [self.store.load(row) for row in db.execute("SELECT * FROM sources WHERE work_id=? AND kind='amendment' AND archived_at IS NOT NULL ORDER BY created", (work_id,))],
                'manifests': self._manifests(db, work_id),
                'expressions': expressions,
                'events': [self.store.load(row) for row in db.execute('SELECT * FROM events WHERE work_id=? ORDER BY id DESC LIMIT 80', (work_id,))],
            }

    def expression(self, expression_id):
        with self.store.transaction() as db:
            return self._expression(db, expression_id)

    def works(self, archived=False):
        with self.store.transaction() as db:
            return [dict(r) for r in db.execute('SELECT * FROM works WHERE archived_at IS '+('NOT NULL' if archived else 'NULL')+' ORDER BY uri')]

    def archive_work(self, work_id, revision, actor, reason):
        self._actor(actor, reason)
        with self.store.transaction() as db:
            self._work(db, work_id, revision)
            self.store.event(db, work_id, 'act_deleted', actor, reason, {})
            db.execute('UPDATE works SET archived_at=? WHERE id=?', (now(), work_id))
            return {'work_id': work_id, 'revision': self._bump(db, work_id)}

    def restore_work(self, work_id, revision, actor, reason):
        self._actor(actor, reason)
        with self.store.transaction() as db:
            work = self._work(db, work_id, revision, allow_archived=True)
            if not work['archived_at']: raise Conflict('Act is already active')
            db.execute('UPDATE works SET archived_at=NULL WHERE id=?', (work_id,))
            self.store.event(db, work_id, 'act_restored', actor, reason, {})
            return {'work_id': work_id, 'revision': self._bump(db, work_id)}

    def archive_amendment(self, work_id, source_id, revision, actor, reason):
        self._actor(actor, reason)
        with self.store.transaction() as db:
            self._work(db, work_id, revision)
            source = db.execute('SELECT * FROM sources WHERE id=? AND work_id=? AND kind=?', (source_id, work_id, 'amendment')).fetchone()
            if source is None: raise ValueError('Amendment not found in this Act')
            if source['archived_at']: raise Conflict('Amendment is already deleted')
            manifest_ids = {row['id'] for row in db.execute('SELECT id FROM manifests WHERE source_id=?', (source_id,))}
            for row in db.execute('SELECT body FROM expressions WHERE work_id=?', (work_id,)):
                body = json.loads(row['body'])
                if source_id in row['body'] or manifest_ids.intersection(body.get('manifest_revisions', {})):
                    raise Conflict('This amendment is used by a saved version. Its version history must be resolved before deletion.')
            db.execute('UPDATE sources SET archived_at=? WHERE id=?', (now(), source_id))
            self.store.event(db, work_id, 'amendment_deleted', actor, reason, {'source_id': source_id})
            return {'source_id': source_id, 'revision': self._bump(db, work_id)}

    def restore_amendment(self, work_id, source_id, revision, actor, reason):
        self._actor(actor, reason)
        with self.store.transaction() as db:
            self._work(db, work_id, revision)
            source = db.execute('SELECT * FROM sources WHERE id=? AND work_id=? AND kind=?', (source_id, work_id, 'amendment')).fetchone()
            if source is None: raise ValueError('Amendment not found in this Act')
            if not source['archived_at']: raise Conflict('Amendment is already active')
            db.execute('UPDATE sources SET archived_at=NULL WHERE id=?', (source_id,))
            self.store.event(db, work_id, 'amendment_restored', actor, reason, {'source_id': source_id})
            return {'source_id': source_id, 'revision': self._bump(db, work_id)}

    def expression_xml(self, expression_id):
        """Inspect a draft or historical expression; this is not an approved export."""
        with self.store.transaction() as db:
            expression=self._expression(db,expression_id)
            return self.store.read(expression['xml_hash'])

    def source_artifact(self, source_id, kind):
        if kind not in {'xml','pdf'}: raise ValueError('Choose xml or pdf')
        with self.store.transaction() as db:
            source=self.store.load(db.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone())
            return self.store.read(source[kind+'_hash'])

    def lookup(self,work_id,as_of,known_at=None):
        iso_date(as_of); cutoff=known_at or now()
        from datetime import datetime
        parsed=datetime.fromisoformat(cutoff)
        if parsed.tzinfo is None: raise ValueError('known_at must include a timezone')
        from datetime import timezone
        cutoff=parsed.astimezone(timezone.utc).isoformat()
        with self.store.transaction() as db:
            self._work(db,work_id)
            row=db.execute('SELECT * FROM expressions WHERE work_id=? AND effective_date<=? AND approved_at<=? AND (invalidated_at IS NULL OR invalidated_at>?) ORDER BY effective_date DESC,approved_at DESC LIMIT 1',(work_id,as_of,cutoff,cutoff)).fetchone()
            expression=self.store.load(row)
            # History cutoff also applies to source and instruction discovery.
            sources=list(db.execute("SELECT id,metadata FROM sources WHERE work_id=? AND kind='amendment' AND archived_at IS NULL AND created<=?",(work_id,cutoff)))
            registered=[r['id'] for r in sources]
            covered=[];unresolved=[];future=[]
            for source in sources:
                source_id=source['id']
                published=json.loads(source['metadata']).get('publication_date')
                m=db.execute('SELECT * FROM manifests WHERE source_id=? AND created<=? ORDER BY revision DESC LIMIT 1',(source_id,cutoff)).fetchone()
                if m is None:
                    (future if published and published>as_of else unresolved).append(source_id)
                    continue
                manifest=self.store.load(m);body=manifest['body']
                applicable=[op for op in body['operations'] if (op.get('effective_date') or body.get('effective_date') or published or '')<=as_of]
                if not applicable:
                    future.append(source_id)
                    continue
                pending=[op for op in applicable if f"{manifest['id']}:{manifest['revision']}:{op['id']}" not in expression['body']['applied']]
                (unresolved if pending else covered).append(source_id)
            return {'expression':expression,'coverage':{'registered_sources':registered,'covered':covered,'unresolved':unresolved,
                    'future_sources':future,'complete_for_registered_sources':not unresolved,
                    'external_completeness':'not established'},'known_at':cutoff,'as_of':as_of}

    def inventory(self,expression_id,target,old,whole_word=False):
        with self.store.transaction() as db:
            expression=self._expression(db,expression_id)
            node=locate(parse(self.store.read(expression['xml_hash'])),target)
            return {'expected_hash':canonical_hash(node),'target_identity':expression['body']['identities'].get(node.get('eId')),
                    'occurrences':public_hits(occurrences(node,old,whole_word))}

    def inspect_instruction(self, manifest_id, expression_id, proposed_body, operation_id):
        """Inspect an unsaved instruction after accepted preceding edits.

        This is diagnostic only. Saving the manifest and applying the full batch
        still reruns every precondition and validation gate.
        """
        with self.store.transaction() as db:
            manifest = self._manifest(db, manifest_id)
            expression = self._expression(db, expression_id)
            if expression['work_id'] != manifest['work_id']:
                raise ValueError('Expression and instrument belong to different works')
            if proposed_body.get('source_id') != manifest['source_id']:
                raise ValueError('Instruction source changed')
            root = parse(self.store.read(expression['xml_hash']))
            identities = dict(expression['body']['identities'])
            tombstones = list(expression['body']['tombstones'])
            operations = proposed_body.get('operations', [])
            if sum(op.get('id') == operation_id for op in operations) != 1:
                raise ValueError('Choose one instruction in this manifest')
            for op in operations:
                if op['id'] == operation_id:
                    break
                if op.get('review_status') != 'accepted':
                    raise Conflict('Review preceding instruction first: ' + op['id'])
                # A later accepted instruction may target a provision inserted
                # here. Use the key that the next saved manifest revision will
                # use so its stable identity matches the full application.
                key = f"{manifest_id}:{manifest['revision'] + 1}:{op['id']}"
                apply_one(root, op, identities, tombstones, key)
            result = {'provisions': [
                {'eid': node.get('eId'), 'tag': tag(node),
                 'num': node.findtext(Q('num')) or '',
                 'heading': node.findtext(Q('heading')) or '',
                 'name': node.get('name'),
                 'excerpt': text(node)[:150]}
                for node in root.iter()
                if tag(node) in {'section', 'subsection', 'clause', 'subclause', 'proviso', 'hcontainer'}
                and node.get('eId')
            ]}
            if not isinstance(op.get('target'), dict):
                result['target_error'] = 'This instruction has no Act target to inspect.'
                return result
            try:
                selected = locate(root, op['target'])
            except (ValueError, KeyError, TypeError) as exc:
                result['target_error'] = str(exc)
                return result
            eid = selected.get('eId')
            target_text = text(selected)
            target_xml = serialise(selected).decode()
            result.update(target_eid=eid, expected_hash=canonical_hash(selected),
                          target_identity=identities.get(eid),
                          target_text=target_text[:3000], target_xml=target_xml[:100000],
                          target_truncated=len(target_text)>3000 or len(target_xml)>100000)
            if op['action'].startswith('text_') and op.get('old'):
                hits = occurrences(selected, op['old'], op.get('whole_word', False))
                result['occurrences'] = public_hits(hits)
                candidate_ids = {el.get('eId') for hit in hits for el, attr, start, end, _ in hit['_slots']
                                 if tag(el) == 'ref' and attr == 'text' and start == 0 and end == len(el.text or '')}
                result['inline_candidates'] = [
                    {'eid': el.get('eId'), 'href': el.get('href'), 'text': el.text}
                    for el in selected.iter(Q('ref')) if el.get('eId') in candidate_ids
                ]
            ids = {el.get('eId') for el in selected.iter() if el.get('eId')}
            result['incoming_references'] = [
                {'eid': ref.get('eId'), 'old_href': ref.get('href'), 'old_text': ref.text}
                for ref in _references(root, ids) if selected not in ref.iterancestors()
            ]
            return result

    def export(self,expression_id):
        with self.store.transaction() as db:
            expression=self._expression(db,expression_id)
            if not expression['approved_at'] or expression['invalidated_at']: raise Conflict('Only a current approved expression can be exported')
            sources=[self.store.load(r) for r in db.execute('SELECT * FROM sources WHERE work_id=? AND archived_at IS NULL',(expression['work_id'],))]
            manifests=[self.store.load(r) for r in db.execute('SELECT m.* FROM manifests m JOIN sources s ON s.id=m.source_id WHERE m.work_id=? AND s.archived_at IS NULL ORDER BY m.id,m.revision',(expression['work_id'],))]
            events=[self.store.load(r) for r in db.execute('SELECT * FROM events WHERE work_id=? ORDER BY id',(expression['work_id'],))]
            history=[self.store.load(r) for r in db.execute('SELECT * FROM expressions WHERE work_id=? ORDER BY created',(expression['work_id'],))]
            bundle={'expression':expression,'expression_history':history,'sources':sources,'instruction_history':manifests,'events':events,'coverage_claim':'Registered sources only; no attestation'}
            files={'consolidated.xml':self.store.read(expression['xml_hash']),'manifest.json':encode(bundle)}
            for version in history:
                files['expressions/'+version['id']+'.xml']=self.store.read(version['xml_hash'])
            for source in sources:
                files['sources/'+source['id']+'.xml']=self.store.read(source['xml_hash'])
                files['sources/'+source['id']+'.pdf']=self.store.read(source['pdf_hash'])
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,raw in sorted(files.items()):
                    info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,raw)
            return output.getvalue()

    def diff(self,left_id,right_id):
        import difflib
        from lxml import etree
        with self.store.transaction() as db:
            left=self._expression(db,left_id);right=self._expression(db,right_id)
            if left['work_id']!=right['work_id']: raise ValueError('Expressions belong to different Acts')
            texts=[etree.tostring(parse(self.store.read(e['xml_hash'])),encoding='unicode',pretty_print=True).splitlines() for e in (left,right)]
            return '\n'.join(difflib.unified_diff(*texts,fromfile=left_id,tofile=right_id,lineterm=''))
