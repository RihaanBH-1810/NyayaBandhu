"""Replay explicit Teachers Act fixture decisions in a fresh local store.

This creates approvals by a test persona. It does not attest legal accuracy.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
from akn_consolidator.service import Consolidator

ROOT = Path(__file__).resolve().parent.parent
AUTH = {'actor':'Fixture reviewer (not legal attestation)', 'reason':'Replay the documented demonstration decisions'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',type=Path,default=ROOT/'consolidation-data'/'teachers-demo')
    parser.add_argument('--output',type=Path,default=None,help='New ZIP path; defaults to STORE/teachers-demo.zip')
    args=parser.parse_args()
    output=args.output or args.store/'teachers-demo.zip'
    c=Consolidator(args.store)
    if c.works(): parser.error('Use a fresh store; existing works are never reset by this demo')
    if output.exists(): parser.error('Output exists; choose a new path')
    reviews=json.loads((ROOT/'tests/fixtures/consolidation/reviews.json').read_text())
    result=c.import_source((ROOT/'out/base_act/eng/tranfer_of_teachers.xml').read_bytes(),
                            (ROOT/'data/v0s/kan_eng/tranfer_of_teachers.pdf').read_bytes(),'base',**AUTH)
    work=result['work_id']
    def approve(result):
        e=result['expression']
        return c.approve(e['id'],result['revision'],e['xml_hash'],**AUTH)
    result=approve(result);parent=result['expression']
    print('Fixture demonstration only: dates and wording choices require independent legal review.')
    print('Base:',parent['id'])
    for name,body in reviews.items():
        imported=c.import_source((ROOT/f'out/amendment/eng/{name}_ammendment.xml').read_bytes(),
                                 (ROOT/f'data/ammendments/{name}_ammendment.pdf').read_bytes(),'amendment',
                                 work_id=work,revision=result['revision'],**AUTH)
        extracted=c.extract(imported['source_id'],imported['revision'],**AUTH);manifest=extracted['manifest']
        reviewed=c.review(manifest['id'],deepcopy(body),extracted['revision'],manifest['revision'],**AUTH)
        preview=c.preview(work,parent['id'],body['effective_date'])
        if not preview['ok']: raise ValueError(json.dumps(preview,indent=2))
        result=approve(c.apply(work,parent['id'],body['effective_date'],reviewed['revision'],preview['preview_hash'],**AUTH))
        parent=result['expression']
        print(f"{name}: {body['effective_date']} | {len(body['operations'])} instructions | valid | {parent['id']}")
    with output.open('xb') as stream: stream.write(c.export(parent['id']))
    print(json.dumps({'work_id':work,'expression_id':parent['id'],'revision':result['revision'],
                      'store':str(args.store),'export':str(output)},indent=2))


if __name__=='__main__': main()
