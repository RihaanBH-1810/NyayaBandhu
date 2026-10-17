"""File-oriented, reviewable interface to the consolidation service."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .service import Consolidator


def parser():
    p = argparse.ArgumentParser(description='Review and consolidate amendment instructions into immutable AKN expressions')
    p.add_argument('--store', default='consolidation-data', help='SQLite/artifact directory (default: consolidation-data)')
    sub = p.add_subparsers(dest='command', required=True)
    def command(name, mutates=False):
        c = sub.add_parser(name)
        if mutates:
            c.add_argument('--actor', required=True)
            c.add_argument('--reason', required=True)
        return c
    c = command('import', True)
    c.add_argument('--xml', type=Path, required=True); c.add_argument('--pdf', type=Path, required=True)
    c.add_argument('--kind', choices=['base','amendment'], required=True)
    c.add_argument('--work'); c.add_argument('--revision', type=int)
    c = command('extract', True); c.add_argument('source'); c.add_argument('--revision', type=int, required=True)
    c = command('review', True); c.add_argument('manifest'); c.add_argument('--file', type=Path, required=True, help='Reviewed manifest body JSON')
    c.add_argument('--revision', type=int, required=True); c.add_argument('--manifest-revision', type=int, required=True)
    for name in ('preview','apply'):
        c = command(name, name=='apply'); c.add_argument('work'); c.add_argument('--parent', required=True); c.add_argument('--date', required=True)
        if name=='apply':
            c.add_argument('--revision', type=int, required=True); c.add_argument('--preview-hash', required=True)
    c = command('approve', True); c.add_argument('expression'); c.add_argument('--revision', type=int, required=True); c.add_argument('--xml-hash', required=True)
    c = command('correct', True); c.add_argument('expression'); c.add_argument('--file', type=Path, required=True, help='JSON with operations and evidence')
    c.add_argument('--revision', type=int, required=True)
    command('works')
    c = command('history'); c.add_argument('work')
    c = command('lookup'); c.add_argument('work'); c.add_argument('--date', required=True); c.add_argument('--known-at')
    c = command('inventory'); c.add_argument('expression'); c.add_argument('--target', required=True, help='JSON target selector')
    c.add_argument('--old', required=True); c.add_argument('--whole-word', action='store_true')
    c = command('diff'); c.add_argument('left'); c.add_argument('right')
    c = command('export'); c.add_argument('expression'); c.add_argument('--output', type=Path, required=True)
    c = command('xml'); c.add_argument('expression'); c.add_argument('--output', type=Path, required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        service = Consolidator(args.store)
        auth = {'actor':args.actor, 'reason':args.reason} if hasattr(args,'actor') else {}
        cmd = args.command
        if cmd=='import':
            result=service.import_source(args.xml.read_bytes(),args.pdf.read_bytes(),args.kind,work_id=args.work,revision=args.revision,**auth)
        elif cmd=='extract': result=service.extract(args.source,args.revision,**auth)
        elif cmd=='review': result=service.review(args.manifest,json.loads(args.file.read_text()),args.revision,args.manifest_revision,**auth)
        elif cmd=='preview': result=service.preview(args.work,args.parent,args.date)
        elif cmd=='apply': result=service.apply(args.work,args.parent,args.date,args.revision,args.preview_hash,**auth)
        elif cmd=='approve': result=service.approve(args.expression,args.revision,args.xml_hash,**auth)
        elif cmd=='correct':
            body=json.loads(args.file.read_text())
            result=service.correct(args.expression,body['operations'],body['evidence'],args.revision,**auth)
        elif cmd=='works': result=service.works()
        elif cmd=='history': result=service.history(args.work)
        elif cmd=='lookup': result=service.lookup(args.work,args.date,args.known_at)
        elif cmd=='inventory': result=service.inventory(args.expression,json.loads(args.target),args.old,args.whole_word)
        elif cmd=='diff': print(service.diff(args.left,args.right)); return 0
        elif cmd in {'xml','export'}:
            raw=service.export(args.expression) if cmd=='export' else service.expression_xml(args.expression)
            # Avoid accidentally overwriting an earlier handoff.
            with args.output.open('xb') as stream: stream.write(raw)
            result={'output':str(args.output),'bytes':len(raw)}
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
