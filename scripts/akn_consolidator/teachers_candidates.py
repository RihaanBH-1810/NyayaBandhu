"""Pinned, unapproved technical drafts for the four distinct Teachers Acts.

This does not register reviewer decisions, approve expressions, or publish law.
It fails closed if a bundled source changes or any XML validation fails.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from .common import canonical_hash, digest, encode, metadata, parse, serialise, validate
from .engine import apply_one, locate, run, seed_identities, update_metadata
from .extraction import extract

ROOT = Path(__file__).resolve().parents[2]
BASE = ('out/base_act/eng/tranfer_of_teachers.xml',
        'data/v0s/kan_eng/tranfer_of_teachers.pdf')
SOURCES = (
    ('First', 'First_ammendment', '2021-04-29'),
    ('Second', 'Second_ammendment', '2022-01-18'),
    ('Teachers_2022', 'Teachers_2022', '2022-10-13'),
    ('Third', 'Third_ammendment', '2026-04-10'),
)
HASHES = {
    BASE[0]: 'd3ff9867142661db4ce8a0aebf314492c6c5dbd63045632ffa7e4cec7e90159a',
    BASE[1]: 'ed28d5b0a2f915d92130f9d0196f7cec78d9db4de91a440b6a948f806cbf8052',
    'out/amendment/eng/First_ammendment.xml': '9edd35cf186fe5563f528dd9d6bf263e5a96cb44cb073d514aace42a742ccbfd',
    'data/ammendments/First_ammendment.pdf': '30fd04892865bf9faa9ab63586cde771f032be5fa9f7d04994f0f97a3fc8232f',
    'out/amendment/eng/Second_ammendment.xml': 'c6c41af1747f168eefde00f75eba5734c2b3d46328656a52a8bf994029a359ca',
    'data/ammendments/Second_ammendment.pdf': '72199013075c4880434d9a714dceee2436a5209ec9b95022af04e6c89d31dc73',
    'out/amendment/eng/Teachers_2022.xml': 'ce0e215bf2b3596e736ccadd562d90cb0980110299ff68949274df181f7f1194',
    'data/ammendments/Teachers_2022.pdf': 'aa615258033adca402148c7dafd50bf581dfe1a7697bdaa49bdda08d25100651',
    'out/amendment/eng/Third_ammendment.xml': 'ed7330964cd9259f6afead127e7e39730414f60b0105d5deb99b59bd2022d5a3',
    'data/ammendments/Third_ammendment.pdf': 'a002050150d69d026f6445eb9f86b1c53e77a4c8314fbf2f1b23e890381bbced',
}
PROFILE = 'data/candidate_profiles/teachers.json'
PROFILE_SHA256 = 'ed9f008407e8e1939c66066a1d97b823fcda741fefc2127aee82228004d6da84'


def checked(path):
    raw = (ROOT / path).read_bytes()
    if digest(raw) != HASHES[path]:
        raise ValueError(f'Bundled source changed: {path}. Candidate generation stopped.')
    return raw


def _rebind(operations, root, identities, tombstones, keys):
    """Rebind the 2026 fixture to the predecessor that includes Act 32 of 2022."""
    trial = deepcopy(root); ids = dict(identities); tombs = list(tombstones)
    for op,key in zip(operations,keys):
        if op.get('target'):
            target = locate(trial, op['target'])
            op['expected_hash'] = canonical_hash(target)
            if 'target_identity' in op:
                op['target_identity'] = ids[target.get('eId')]
        apply_one(trial, op, ids, tombs, key)


def build_candidate_package():
    """Return a self-contained ZIP and report. No CMS state is changed."""
    base_xml, base_pdf = (checked(path) for path in BASE)
    profile_raw = (ROOT / PROFILE).read_bytes()
    if digest(profile_raw) != PROFILE_SHA256:
        raise ValueError('Candidate decision profile changed; review it before updating the pinned hash')
    profiles = json.loads(profile_raw)
    root = parse(base_xml)
    report = validate(root)
    if not report['ok']:
        raise ValueError('Bundled base XML failed validation: ' + report['summary'])
    work_id = digest(metadata(root)['work_uri'].encode())[:24]
    identities = seed_identities(root,work_id); tombstones = []
    files = {'sources/base.xml':base_xml,'sources/base.pdf':base_pdf,
             'drafts/00-base.xml':base_xml,'profiles/teachers.json':profile_raw}
    versions = []; seen_uris = set()
    for index,(name,stem,day) in enumerate(SOURCES,1):
        xml_path=f'out/amendment/eng/{stem}.xml'
        pdf_path=f'data/ammendments/{stem}.pdf'
        xml,pdf=checked(xml_path),checked(pdf_path)
        source_root=parse(xml);uri=metadata(source_root)['work_uri']
        if uri in seen_uris: raise ValueError('Duplicate amending Act Work URI: '+uri)
        seen_uris.add(uri)
        source_id=digest(encode([work_id,'amendment',digest(xml),digest(pdf)]))[:24]
        manifest_id=digest((source_id+':instructions').encode())[:24]
        extracted=extract(source_root,pdf)
        body=deepcopy(profiles[name]) if name in profiles else extracted
        if body['source_work_uri']!=uri or len(body['coverage'])!=len(extracted['coverage']):
            raise ValueError('Candidate profile does not match '+name)
        operations=body['operations']
        if any(op['action']=='blocked' or not op['source'].get('pdf_pages') or not op['source'].get('quote') for op in operations):
            raise ValueError('Unresolved operation or source evidence in '+name)
        keys=[f'{manifest_id}:2:{op["id"]}' for op in operations]
        if name=='Third': _rebind(operations,root,identities,tombstones,keys)
        new_root,result=run(root,list(zip(keys,operations)),identities,tombstones)
        if not result['ok']:
            raise ValueError('Candidate application blocked in '+name+': '+json.dumps(result['conflicts']))
        modifications=[{'operation':op,'change':change,'source_uri':uri}
                       for op,change in zip(operations,result['changes'])]
        update_metadata(new_root,day,[{'date':day,'work_uri':uri}],modifications)
        checked_result=validate(new_root)
        if not checked_result['ok']:
            raise ValueError('Candidate XML invalid after '+name+': '+checked_result['summary'])
        root,identities,tombstones=new_root,result['identities'],result['tombstones']
        output=f'drafts/{index:02d}-{stem}.xml'
        files[output]=serialise(root)
        files[f'sources/{stem}.xml']=xml; files[f'sources/{stem}.pdf']=pdf
        versions.append({'instrument':name,'work_uri':uri,'candidate_date':day,
                         'date_basis':'technical fixture assumption; requires legal review',
                         'operation_count':len(operations),'source_sha256':{'xml':digest(xml),'pdf':digest(pdf)},
                         'draft_sha256':digest(files[output]),'validation':checked_result,'draft_file':output,
                         'profile_basis':'technical test profile, not lawyer-certified' if name in profiles else 'extractor proposal, not reviewed'})
    summary={'status':'unapproved_technical_candidates','base_work_uri':metadata(parse(base_xml))['work_uri'],
             'profile_sha256':digest(profile_raw),'versions':versions,
             'warning':'Dates and instruction interpretations require lawyer review. No XML in this package is approved or published.'}
    files['report.json']=encode(summary)
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for path,raw in sorted(files.items()):
            info=ZipInfo(path,date_time=(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            archive.writestr(info,raw)
    return output.getvalue(),summary


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Build unapproved Teachers Act candidate XML and evidence ZIP')
    parser.add_argument('--output',type=Path,default=Path('teachers-unapproved-candidates.zip'))
    args=parser.parse_args()
    raw,report=build_candidate_package()
    args.output.write_bytes(raw)
    print(json.dumps({'output':str(args.output),'status':report['status'],
                      'instruments':[v['work_uri'] for v in report['versions']]},indent=2))


if __name__=='__main__':
    main()
