"""Conservative instruction candidates from English gazette text.

Quotes delimit replacement material, not instructions. Every outer section is
covered, including unsupported instructions and separate legal effects.
"""
from __future__ import annotations
import re
from datetime import datetime
import pymupdf
from .common import Q, NS, text, metadata

ORDINALS = {'first':'1', 'second':'2', 'third':'3', 'fourth':'4', 'fifth':'5', 'sixth':'6'}
KINDS = {'section':'section', 'sub-section':'subsection', 'subsection':'subsection', 'clause':'clause', 'proviso':'proviso'}


def compact(value):
    return re.sub(r'\s+', ' ', value).strip()


def replacement_payload(instruction):
    payload = instruction.split('namely', 1)[1].lstrip(',:- \t').strip()
    if payload.startswith('"'):
        closing = payload.rfind('"')
        if closing > 0 and re.fullmatch(r'\s*[.;,]?\s*', payload[closing + 1:]):
            return payload[1:closing].strip()
    return payload.strip('"').strip()


def quoted_fragment(payload, kind):
    payload = payload.strip().strip('“”"').strip()
    spec = {'tag': kind}
    if kind == 'section':
        match = re.match(r'(\d+[A-Z]?)\.\s*(.*?)\.-\s*(.*)', payload, re.S)
        if not match: raise ValueError('Replacement section heading needs review')
        spec.update(num=match[1] + '.', heading=match[2]); payload = match[3]
    elif kind != 'proviso':
        match = re.match(r'\(([^)]+)\)\s*(.*)', payload, re.S)
        if not match: raise ValueError('Inserted provision number needs review')
        spec['num'] = '(' + match[1] + ')'; payload = match[2]
    provisos = list(re.finditer(r'\bProvided(?:\s+also|\s+further)?\s+that\b', payload))
    if kind != 'proviso' and provisos:
        spec['text'] = payload[:provisos[0].start()].strip()
        spec['children'] = [{'tag':'proviso', 'text':payload[m.start():provisos[i+1].start() if i+1<len(provisos) else len(payload)].strip()}
                            for i,m in enumerate(provisos)]
    else:
        parts = list(re.finditer(r'\(([ivx]+|[a-z]|\d+)\)\s+(?=[A-Z])', payload))
        if parts and ('namely' in payload[:parts[0].start()] or payload[:parts[0].start()].rstrip().endswith(':')):
            spec['text'] = payload[:parts[0].start()].strip()
            spec['children'] = [quoted_fragment(payload[m.start():parts[i+1].start() if i+1<len(parts) else len(payload)].strip(), 'subclause' if kind == 'clause' else 'clause') for i,m in enumerate(parts)]
        else: spec['text'] = payload
    return spec


def _split_instructions(content):
    # Mark positions outside typographic quotations. A straight closing quote
    # is accepted for PDFs mixing typographic opening and straight closing.
    depth = 0; outside = []
    for c in content:
        outside.append(depth == 0)
        if c == '“': depth += 1
        elif c == '”' or (c == '"' and depth): depth = max(0, depth-1)
    markers = [m.start() for m in re.finditer(r'\([a-z0-9-]+\)\s+(?=(?:in|after|before|for|clause)\b)', content, re.I) if outside[m.start()]]
    boundaries = [0] + markers + [len(content)]
    return [content[a:b].strip() for a,b in zip(boundaries,boundaries[1:]) if content[a:b].strip()]


def _path_context(segment, path):
    result = list(path)
    for match in re.finditer(r'\bin\s+(section|sub-section|subsection|clause)\s*\(?([\da-z-]+)\)?', segment, re.I):
        kind = KINDS[match[1].lower()]; label = match[2]
        ranks = {'section':0,'subsection':1,'clause':2}
        result = [x for x in result if ranks.get(x[0],3) < ranks[kind]] + [[kind,label]]
    return result


def _target(path): return {'path': path}


def _tables(section):
    return [[[text(cell) for cell in row] for row in table] for table in section.iter(Q('table'))]


def interpret(segment, path, section, heading):
    s = compact(segment).replace('“','"').replace('”','"')
    s = re.sub(r'sub-\s+section', 'sub-section', s, flags=re.I)
    s = re.sub(r'^\([a-z0-9-]+\)\s*', '', s)
    path = _path_context(s.split('namely',1)[0], path)
    scope = {'region':'schedule'} if 'schedule' in heading.lower() else _target(path)
    rename = re.search(r'clause\s*\(([^)]+)\).*?renumbered as\s*\(([^)]+)\)',s,re.I)
    if rename:
        return [{'action':'renumber','target':_target(path + [['clause',rename[1]]]),'new_number':'('+rename[2]+')'}],path
    strings = re.findall(r'"([^"]*)"', s)
    if 'substituted' in s and 'the word' in s and len(strings) >= 2:
        if 'long title and preamble' in s.lower():
            return [{'action':'text_replace','target':{'region':r},'old':strings[0],'new':strings[1],'count':1} for r in ('longTitle','preamble')],path
        whole = 'wherever' in s
        return [{'action':'text_replace','target':{'region':'act'} if whole else scope,'old':strings[0],'new':strings[1],
                 'count':None if whole else 1, 'global':whole, 'whole_word':True}],path
    if 'inserted' in s and re.search(r'(after|before) the words?\b',s,re.I) and len(strings)>=2:
        position = re.search(r'(after|before) the words?\b',s,re.I)[1].lower()
        return [{'action':'text_insert','target':scope,'old':strings[0],'new':(' ' + strings[1]) if position=='after' else strings[1]+' ', 'position':position,'count':1}],path
    if 'omitted' in s and 'the word' in s and strings:
        return [{'action':'text_omit','target':scope,'old':strings[0],'new':'','count':1}],path
    omitted = re.search(r'clause\s*\(([^)]+)\).*shall be omitted',s,re.I)
    if omitted:
        return [{'action':'omit_provision','target':_target(path + [['clause',omitted[1]]])}],path
    if re.search(r'shall be (?:inserted|substituted)',s) and 'namely' in s:
        # Gazette formulas also use "namely,-" and "namely:-". Keep
        # punctuation outside the closing quotation out of the new law text.
        payload = replacement_payload(s)
        item = re.search(r'for\s+item\s*\(([^)]+)\)', s, re.I)
        if item and 'substituted' in s:
            # An item inside a clause is a subclause in AKN. A replacement may
            # print an additional item immediately after the old one.
            markers = list(re.finditer(r'\(([ivxlcdm]+(?:-[a-z])?)\)\s+(?=[A-Z])', payload, re.I))
            if not markers or markers[0][1].casefold() != item[1].casefold() or markers[0].start() != 0:
                raise ValueError('Replacement item numbering needs review')
            fragments = [quoted_fragment(payload[m.start():markers[i+1].start() if i+1<len(markers) else len(payload)], 'subclause')
                         for i,m in enumerate(markers)]
            target = _target(path + [['subclause', item[1]]])
            operations = [{'action':'replace_provision','target':target,'fragment':fragments[0]}]
            if len(fragments) > 1:
                operations.append({'action':'insert_provision','target':target,
                                   'position':'after','fragments':fragments[1:]})
            return operations,path
        if 'schedule' in heading.lower():
            tables = _tables(section)
            if not tables: raise ValueError('Schedule table could not be recovered')
            if 'SCHEDULE-II' in payload:
                return [{'action':'schedule_add','target':{'region':'schedule'},'fragment':{'tag':'hcontainer','name':'schedule','heading':'SCHEDULE-II','subheading':'(see section 2 and 16)','table':tables[-1]}}],path
            anchor = re.search(r'after serial number\s+([IVX]+)',s)
            if not anchor: raise ValueError('Schedule insertion anchor needs review')
            return [{'action':'table_insert','target':{'region':'schedule','label':'SCHEDULE-I'},'after_group':anchor[1],'rows':tables[-1]}],path
        pair = re.search(r'for\s+(first|second|third|fourth|fifth|sixth)\s+and\s+'
                         r'(first|second|third|fourth|fifth|sixth)\s+provisos?\b', s, re.I)
        if pair:
            first, second = int(ORDINALS[pair[1].lower()]), int(ORDINALS[pair[2].lower()])
            if first < 2 or second != first + 1 or not re.match(r'Provided\b', payload):
                raise ValueError('Multiple proviso substitution needs review')
            # Remove the later provision first: proviso selectors use document
            # order, so removing the earlier one would shift the later target.
            return [
                {'action':'omit_provision','target':_target(path + [['proviso',str(second)]])},
                {'action':'omit_provision','target':_target(path + [['proviso',str(first)]])},
                {'action':'insert_provision','target':_target(path + [['proviso',str(first - 1)]]),
                 'position':'after','fragments':[quoted_fragment(payload,'proviso')]},
            ],[part for part in path if part[0] == 'section']
        replacement = re.search(r'for\s+(section|sub-section|subsection|clause)\s*\(?([\da-z-]+)\)?',s,re.I)
        if replacement:
            kind = KINDS[replacement[1].lower()]; label = replacement[2]
            target_path = [[kind,label]] if kind=='section' else path + [[kind,label]]
            return [{'action':'replace_provision','target':_target(target_path),'fragment':quoted_fragment(payload,kind)}],path
        anchor = re.search(r'(after|before)\s+(section|sub-section|subsection|clause)\s*\(?([\da-z-]+)\)?',s,re.I)
        ordinal = re.search(r'after\s+(first|second|third|fourth|fifth) proviso',s,re.I)
        kind = 'proviso' if 'proviso' in s.split('namely')[0] else (KINDS[anchor[2].lower()] if anchor else None)
        if anchor:
            anchor_kind = KINDS[anchor[2].lower()]
            ranks = {'section':0,'subsection':1,'clause':2}
            target_path = [x for x in path if ranks.get(x[0],3) < ranks[anchor_kind]] + [[anchor_kind,anchor[3]]]
            position = anchor[1].lower()
        elif ordinal:
            target_path = path + [['proviso',ORDINALS[ordinal[1].lower()]]]; position='after'; kind='proviso'
        elif 'at the end' in s:
            target_path = path; position='last_child'; kind='proviso'
        else: raise ValueError('Insertion position needs review')
        if kind == 'proviso':
            starts = list(re.finditer(r'\bProvided(?:\s+also|\s+further)?\s+that\b',payload))
            if not starts: raise ValueError('Proviso wording needs review')
            fragments = [quoted_fragment(payload[m.start():starts[i+1].start() if i+1<len(starts) else len(payload)],'proviso') for i,m in enumerate(starts)]
        else: fragments=[quoted_fragment(payload,kind)]
        return [{'action':'insert_provision','target':_target(target_path),'position':position,'fragments':fragments}],path
    if not re.search(r'\b(inserted|substituted|omitted|renumbered)\b',s):
        return [],path
    raise ValueError('Instruction pattern needs review')


def extract(xml_root, pdf_bytes):
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    chunks, page_offsets = [], []
    length = 0
    for i,page in enumerate(doc):
        value = re.sub(r'(?m)^\s*\d+\s*$', '', page.get_text())
        page_offsets.append((length, i+1)); chunks.append(value); length += len(value)+1
    raw = '\n'.join(chunks); start = raw.find('KARNATAKA ACT NO.')
    if start < 0: raise ValueError('English Act text not found in PDF; OCR or review required')
    end = raw.find('The above translation',start)
    if end < 0: end=len(raw)
    body = raw[start:end]
    boundaries = list(re.finditer(r'(?m)^\s*(\d+)\.\s+(Short title|Amendment|Substitution|Repeal)\b',body))
    sections = {normalise_section(e.findtext(Q('num'))):e for e in xml_root.findall('./'+Q('act')+'/'+Q('body')+'/'+Q('section'))}
    operations, coverage = [], []
    match = re.search(r'(?:Karnataka Act\s+0*(\d+)\s+of\s+(\d{4}))',body,re.I)
    target_identity = {'jurisdiction':'in-ka','number':match[1],'year':match[2]} if match else None
    date_match = re.search(r'effect from\s+(\d+)\w*\s+day of\s+(\w+)\s+(\d{4})',compact(body),re.I)
    effective = datetime.strptime(' '.join(date_match.groups()),'%d %B %Y').date().isoformat() if date_match else None
    for index,m in enumerate(boundaries):
        number = m[1]; source_eid='sec_'+number
        section = sections.get(number)
        finish = boundaries[index+1].start() if index+1<len(boundaries) else len(body)
        chunk = body[m.start():finish]
        absolute_start, absolute_end = start+m.start(), start+finish
        pages = [page for offset,page in page_offsets if offset < absolute_end and (page == len(page_offsets) or page_offsets[page][0] > absolute_start)]
        heading = section.findtext(Q('heading')) if section is not None else m[2]
        provenance = {'source_eid':source_eid, 'pdf_pages':pages, 'quote':compact(chunk)}
        coverage.append({'source_eid':source_eid,'heading':heading,'pdf_pages':pages})
        if heading and ('commencement' in heading.lower() or 'repeal and savings' in heading.lower()):
            candidates=[{'action':'effect','classification':'commencement' if 'commencement' in heading.lower() else 'repeal_and_savings','details':compact(chunk)}]
        elif section is None:
            candidates=[{'action':'blocked','issue':'Source XML section missing'}]
        else:
            target_section = re.search(r'section\s+(\d+[A-Z]?)',heading or '',re.I)
            path = [['section',target_section[1]]] if target_section else []
            content = re.sub(r'^\s*\d+\.\s*.*?\.-\s*','',chunk,count=1,flags=re.S)
            candidates=[]
            for segment in _split_instructions(content):
                try:
                    extracted,path=interpret(segment,path,section,heading or '')
                    candidates.extend(extracted)
                except ValueError as exc:
                    candidates.append({'action':'blocked','issue':str(exc),'unparsed':compact(segment)})
            if not candidates: candidates=[{'action':'blocked','issue':'No supported instruction found'}]
        for candidate in candidates:
            if candidate['action'].startswith('text_'):
                candidate.setdefault('whole_word', True)
            operations.append({'id':f'{source_eid}_op_{1+sum(o["source"]["source_eid"]==source_eid for o in operations)}',
                               'review_status':'pending', 'source':provenance, **candidate})
    missing = sorted(set(sections) - {normalise_section(x['source_eid'].replace('sec_','')) for x in coverage})
    for number in missing:
        eid='sec_'+number
        coverage.append({'source_eid':eid,'heading':sections[number].findtext(Q('heading')),'pdf_pages':[]})
        operations.append({'id':eid+'_op_1','action':'blocked','issue':'PDF section boundary not recovered',
                           'review_status':'pending','source':{'source_eid':eid,'pdf_pages':[],'quote':text(sections[number])}})
    return {'format_version':1, 'status':'needs_review','target_identity':target_identity,'identity_confirmed':False,
            'effective_date':effective,'date_confirmed':False,
            'date_evidence':date_match[0] if date_match else 'Commencement requires a recorded date determination',
            'coverage':coverage,'operations':operations, 'source_work_uri':metadata(xml_root)['work_uri']}


def normalise_section(number):
    return (number or '').strip().rstrip('.')
