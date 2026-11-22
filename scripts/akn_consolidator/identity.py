"""Conservative principal-Act matching for an amending instrument."""
import re
import pymupdf
from .common import Q, text

TARGET = re.compile(r"\b(?:further\s+)?amend(?:ing|ment to)?\s+(?:the\s+)?(.{0,180}?)\s+Act\s*,?\s*(\d{4})\b", re.I | re.S)
CITATION = re.compile(r"\bKarnataka\s+Act\s+(?:No\.?\s*)?0*(\d+)\s+of\s+(\d{4})\b", re.I)


def check(root, pdf, base_uri, base_title=''):
    """Return match/unclear/mismatch, never treating an incidental citation as proof."""
    act = root.find(Q('act'))
    headings = []
    if act is not None:
        for name in ('longTitle', 'preamble'):
            el = act.find(Q(name))
            if el is not None: headings.append(text(el))
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        pages = [page.get_text() for page in doc]
    candidates = []
    for origin,passage in [('xml',p) for p in headings]+[('pdf',p) for p in pages]:
        for match in TARGET.finditer(passage):
            nearby = passage[match.start():match.end()+110]
            cite = CITATION.search(nearby)
            candidates.append({'origin':origin,'title': match[1].strip(), 'citation': cite.groups() if cite else None,
                               'excerpt': passage[max(0,match.start()-40):min(len(passage),match.end()+110)].strip()})
    parts = base_uri.split('/')
    expected = (str(int(parts[-1])), parts[-2][:4])
    def norm(s): return re.sub(r'[^a-z0-9]', '', s.casefold())
    base_name = norm(re.sub(r'\bAct\b.*$', '', base_title, flags=re.I))
    hits = []
    for item in candidates:
        cite = item['citation']
        hits.append((str(int(cite[0])),cite[1]) == expected if cite else bool(base_name and norm(item['title']) in base_name))
    cited = [hit for item,hit in zip(candidates,hits) if item['citation']]
    pdf_cited = [hit for item,hit in zip(candidates,hits) if item['origin']=='pdf' and item['citation']]
    if cited and not any(cited): status = 'mismatch'
    elif cited and not all(cited): status = 'unclear'
    elif pdf_cited and all(pdf_cited): status = 'match'
    else: status = 'unclear'
    return {'status':status, 'expected':base_uri, 'candidates':candidates}
