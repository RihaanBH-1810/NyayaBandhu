"""Pure XML transformations; never writes to storage or accepts guessed matches."""
from __future__ import annotations

from copy import deepcopy
import difflib
import re
from lxml import etree
from akn_parser.eids import element_ref, normalise_num
from .common import Q, NS, Conflict, tag, text, canonical_hash, digest, encode, validate

PROVISIONS = {'section', 'subsection', 'clause', 'subclause', 'proviso', 'hcontainer'}


def locate(root, selector):
    if selector.get('eid'):
        found = root.xpath('//*[@eId=$eid]', eid=selector['eid'])
    elif selector.get('region'):
        region = selector['region']
        if region == 'act':
            found = root.findall(Q('act'))
        elif region in {'longTitle', 'preamble'}:
            found = root.findall('.//' + Q(region))
        elif region == 'schedule':
            found = [e for e in root.iter(Q('hcontainer')) if e.get('name') == 'schedule']
            label = selector.get('label')
            if label:
                found = [e for e in found if text(e.find(Q('heading'))).casefold() == label.casefold()]
        else:
            raise Conflict('Unknown region')
    else:
        found = [root]
        for kind, label in selector.get('path', []):
            candidates = []
            for parent in found:
                children = list(parent.iter(Q(kind))) if parent is root else list(parent.findall(Q(kind)))
                if kind == 'proviso':
                    index = int(label) - 1
                    candidates.extend(children[index:index+1] if index >= 0 else [])
                else:
                    candidates.extend(e for e in children if normalise_num(e.findtext(Q('num')) or '') == normalise_num(label))
            found = candidates
        if found == [root]:
            raise Conflict('Empty target selector')
    if len(found) != 1:
        raise Conflict(f'Target must resolve once; found {len(found)} for {selector}')
    return found[0]


def seed_identities(root, work_id):
    return {e.get('eId'): digest((work_id + ':' + e.get('eId')).encode())[:24]
            for e in root.iter() if e.get('eId')}


def _slots(field):
    result = []
    def walk(el, protected=False):
        if el.text:
            result.append((el, 'text', el.text, protected))
        for child in el:
            if isinstance(child.tag, str): walk(child, True)
            if child.tail:
                result.append((child, 'tail', child.tail, protected))
    walk(field)
    return result


def _normal_map(raw):
    chars, mapping = [], []
    for i, c in enumerate(raw):
        if c.isspace():
            if chars and chars[-1] == ' ':
                mapping[-1][1] = i + 1
                continue
            c = ' '
        chars.append(c); mapping.append([i, i+1])
    return ''.join(chars), mapping


def occurrences(target, needle, whole_word=False):
    if not needle:
        raise Conflict('Empty text anchor')
    needle = re.sub(r'\s+', ' ', needle)
    hits = []
    for field in target.iter():
        if tag(field) not in {'p', 'heading', 'subheading', 'num'}:
            continue
        if any(tag(a) == 'meta' for a in field.iterancestors()):
            continue
        slots = _slots(field)
        combined = ''.join(s[2] for s in slots)
        normal, mapping = _normal_map(combined)
        pattern = re.escape(needle)
        if whole_word:
            pattern = r'(?<!\w)' + pattern + r'(?!\w)'
        for match in re.finditer(pattern, normal):
            start, end = mapping[match.start()][0], mapping[match.end()-1][1]
            cursor = 0; involved = []
            for el, attr, raw, protected in slots:
                if cursor < end and cursor + len(raw) > start:
                    involved.append((el, attr, max(0, start-cursor), min(len(raw), end-cursor), protected))
                cursor += len(raw)
            hits.append({'field': field.get('eId') or field.getparent().get('eId'),
                         'offset': start, 'text': combined[start:end],
                         'protected': any(x[4] for x in involved),
                         'cross_inline': len(involved) != 1, '_slots': involved})
    return hits


def public_hits(hits):
    return [{k:v for k,v in h.items() if not k.startswith('_')} for h in hits]


def _text_operation(node, op):
    hits = occurrences(node, op['old'], op.get('whole_word', False))
    inventory = public_hits(hits)
    expected = op.get('occurrences')
    if expected is not None and expected != inventory:
        raise Conflict('Occurrence inventory changed; review the new matches')
    if op.get('global') and expected is None:
        raise Conflict('Whole-Act substitution requires an approved occurrence inventory')
    if len(hits) != op.get('count', 1):
        raise Conflict(f"Expected {op.get('count', 1)} text match(es), found {len(hits)}")
    removals = op.get('inline_removals', [])
    if removals:
        if op['action'] != 'text_omit' or expected is None or not op.get('allow_protected'):
            raise Conflict('Inline omission requires an approved inventory and protected-text decision')
        nodes = []
        for removal in removals:
            el = locate(node, {'eid': removal['eid']})
            if tag(el) != 'ref' or len(el) or el.get('href') != removal['href'] or el.text != removal['text']:
                raise Conflict('Inline removal precondition changed')
            if not any(e is el and attr == 'text' and start == 0 and end == len(el.text or '')
                       for hit in hits for e, attr, start, end, _ in hit['_slots']):
                raise Conflict('Inline removal must be entirely covered by the omission')
            nodes.append(el)
        if len({el.get('eId') for el in nodes}) != len(nodes):
            raise Conflict('Duplicate inline removal')
        for hit in hits:
            for el, attr, start, end, protected in hit['_slots']:
                if protected and (attr != 'text' or el not in nodes):
                    raise Conflict('Omission affects another protected element')
        for hit in reversed(hits):
            for el, attr, start, end, _ in reversed(hit['_slots']):
                raw = getattr(el, attr)
                setattr(el, attr, raw[:start] + raw[end:])
        for el in nodes:
            parent = el.getparent(); previous = el.getprevious()
            if previous is None: parent.text = (parent.text or '') + (el.tail or '')
            else: previous.tail = (previous.tail or '') + (el.tail or '')
            parent.remove(el)
        return inventory
    if any(h['cross_inline'] for h in hits):
        raise Conflict('Match crosses inline boundaries; submit explicit slot_edits')
    if any(h['protected'] for h in hits) and not (expected is not None and op.get('allow_protected')):
        raise Conflict('Match affects protected inline text; approve the occurrence inventory explicitly')
    for hit in reversed(hits):
        el, attr, start, end, _ = hit['_slots'][0]
        raw = getattr(el, attr)
        new = op.get('new', '')
        if op['action'] == 'text_insert':
            new = (raw[start:end] + new) if op.get('position', 'after') == 'after' else (new + raw[start:end])
        setattr(el, attr, raw[:start] + new + raw[end:])
    return inventory


def _ids(root):
    return {e.get('eId') for e in root.iter() if e.get('eId')}


def _references(root, ids):
    work = root.find('./' + Q('act') + '/' + Q('meta') + '/' + Q('identification') + '/' + Q('FRBRWork') + '/' + Q('FRBRuri'))
    uri = work.get('value') if work is not None else ''
    for el in root.iter(Q('ref')):
        href = el.get('href', '')
        if '#' in href and href.rsplit('#', 1)[1] in ids and (href.startswith('#') or (uri and (href.startswith(uri + '/') or href.startswith(uri + '#')))):
            yield el


def _reference_decisions(root, changed_ids, updates, removed_subtree=None):
    refs = [r for r in _references(root, changed_ids)
            if removed_subtree is None or removed_subtree not in r.iterancestors()]
    submitted = {u['eid']: u for u in updates}
    if {r.get('eId') for r in refs} != set(submitted):
        if refs or submitted:
            raise Conflict('Incoming references require explicit href and displayed-text decisions: ' + ', '.join(r.get('eId', '') for r in refs))
    for ref in refs:
        decision = submitted[ref.get('eId')]
        if len(ref) or ref.get('href') != decision['old_href'] or ref.text != decision['old_text']:
            raise Conflict('Reference precondition changed')
        if not decision.get('resolved_by'):
            ref.set('href', decision['new_href']); ref.text = decision['new_text']


def _rename(root, node, new_id, identities, updates=()):
    old = node.get('eId')
    mapping = {e.get('eId'): new_id + e.get('eId')[len(old):] for e in node.iter() if e.get('eId')}
    if any(not (x == old or x.startswith(old + '__')) for x in mapping):
        raise Conflict('Subtree contains unrelated identifiers')
    if set(mapping.values()) & (_ids(root) - set(mapping)):
        raise Conflict('Renumbering collides with existing identifiers')
    _reference_decisions(root, set(mapping), updates)
    for el in node.iter():
        eid = el.get('eId')
        if eid:
            el.set('eId', mapping[eid])
            if eid in identities:
                identities[mapping[eid]] = identities.pop(eid)
    return mapping


def _stamp(root, node, prefix, operation_key, identities):
    counters = {}
    def walk(el, parent_id):
        kind = tag(el)
        if kind in {'num', 'heading', 'meta', 'identification', 'doc'}:
            for child in el:
                walk(child, parent_id)
            return
        number = normalise_num(el.findtext(Q('num')) or '')
        key = (parent_id, kind)
        counters[key] = counters.get(key, 0) + 1
        suffix = number or str(counters[key])
        local = element_ref(kind) + '_' + suffix
        if kind in {'content', 'intro', 'wrapUp', 'mainBody'}:
            local = element_ref(kind)
        eid = parent_id + '__' + local if parent_id else local
        while eid in _ids(root) or eid in identities:
            if number:
                raise Conflict(f'Inserted provision identifier already exists: {eid}')
            counters[key] += 1
            eid = (parent_id + '__' if parent_id else '') + element_ref(kind) + '_' + str(counters[key])
        el.set('eId', eid)
        identities[eid] = digest((operation_key + ':' + eid).encode())[:24]
        for child in el:
            walk(child, eid)
    walk(node, prefix)


def fragment(spec):
    kind = spec['tag']
    if kind not in PROVISIONS | {'table', 'tr', 'td', 'th'}:
        raise Conflict(f'Unsupported fragment kind {kind}')
    node = etree.Element(Q(kind))
    if kind == 'hcontainer': node.set('name', spec.get('name', 'schedule'))
    if spec.get('num'): etree.SubElement(node, Q('num')).text = spec['num']
    if spec.get('heading'): etree.SubElement(node, Q('heading')).text = spec['heading']
    if spec.get('subheading'): etree.SubElement(node, Q('subheading')).text = spec['subheading']
    if kind == 'table':
        for row in spec['rows']:
            tr = etree.SubElement(node, Q('tr'))
            for cell in row:
                td = etree.SubElement(tr, Q('td')); etree.SubElement(td, Q('p')).text = cell
        return node
    if kind in {'td', 'th'}:
        etree.SubElement(node, Q('p')).text = spec.get('text', '')
        return node
    children = spec.get('children', [])
    if spec.get('table'):
        content = etree.SubElement(node, Q('content'))
        content.append(fragment({'tag':'table','rows':spec['table']}))
        return node
    if spec.get('text') or not children:
        wrap = etree.SubElement(node, Q('intro' if children else 'content'))
        etree.SubElement(wrap, Q('p')).text = spec.get('text', '')
    for child in children: node.append(fragment(child))
    return node


def _container_for_child(root, parent, identities, op):
    content = parent.find(Q('content'))
    if content is not None:
        _rename(root, content, parent.get('eId') + '__intro', identities, op.get('container_reference_updates', []))
        content.tag = Q('intro')


def apply_one(root, op, identities, tombstones, operation_key):
    action = op['action']
    if action == 'effect': return {'effect': op['classification']}
    if action == 'blocked': raise Conflict(op.get('issue', 'Unsupported instruction'))
    node = locate(root, op['target'])
    before_id = node.get('eId')
    if op.get('expected_hash') and canonical_hash(node) != op['expected_hash']:
        raise Conflict('Target content hash changed')
    if op.get('target_identity') and identities.get(before_id) != op['target_identity']:
        raise Conflict('Target provision identity changed')
    before = text(node)
    details = {}
    if action in {'text_replace', 'text_omit', 'text_insert'}:
        details['occurrences'] = _text_operation(node, op)
        for removal in op.get('inline_removals', []):
            eid = removal['eid']
            tombstones.append({'identity': identities.pop(eid, None), 'eid': eid, 'operation': operation_key})
    elif action == 'slot_edits':
        for edit in op['edits']:
            el = locate(node, {'eid': edit['eid']})
            if el is not node and node not in el.iterancestors(): raise Conflict('Slot is outside target')
            attr = edit['slot']
            if attr not in {'text', 'tail'} or getattr(el, attr) != edit['before']:
                raise Conflict('Slot precondition changed')
            setattr(el, attr, edit['after'])
    elif action == 'renumber':
        num = node.find(Q('num'))
        if num is None: raise Conflict('Target has no printed number')
        token = normalise_num(op['new_number'])
        parent_prefix = node.get('eId').rsplit('__', 1)[0] + '__' if '__' in node.get('eId') else ''
        details['identifier_mapping'] = _rename(root, node, parent_prefix + element_ref(tag(node)) + '_' + token, identities, op.get('reference_updates', []))
        num.text = op['new_number']
    elif action in {'omit_provision', 'replace_provision'}:
        old_ids = _ids(node)
        check_ids = old_ids if action == 'omit_provision' else old_ids - {before_id}
        _reference_decisions(root, check_ids, op.get('reference_updates', []), removed_subtree=node)
        for eid in old_ids:
            tombstones.append({'identity': identities.pop(eid, None), 'eid': eid, 'operation': operation_key})
        parent = node.getparent(); index = parent.index(node); tail = node.tail
        parent.remove(node)
        if action == 'replace_provision':
            replacement = fragment(op['fragment'])
            prefix = before_id.rsplit('__', 1)[0] if '__' in before_id else ''
            _stamp(root, replacement, prefix, operation_key, identities)
            if replacement.get('eId') != before_id:
                raise Conflict('Replacement must retain the provision number')
            original = next(x for x in reversed(tombstones) if x['eid'] == before_id)
            identities[before_id] = original['identity']; tombstones.remove(original)
            replacement.tail = tail; parent.insert(index, replacement); node = replacement
    elif action == 'insert_provision':
        position = op.get('position', 'after')
        parent = node if position == 'last_child' else node.getparent()
        if position == 'last_child': _container_for_child(root, parent, identities, op)
        specs = op.get('fragments') or [op['fragment']]
        index = len(parent) if position == 'last_child' else parent.index(node) + (position == 'after')
        if position not in {'after', 'before', 'last_child'}: raise Conflict('Invalid insertion position')
        for spec in specs:
            added = fragment(spec)
            prefix = parent.get('eId', '')
            _stamp(root, added, prefix, operation_key, identities)
            parent.insert(index, added); index += 1
    elif action == 'schedule_add':
        act = root.find(Q('act')); attachments = act.find(Q('attachments'))
        if attachments is None: attachments = etree.SubElement(act, Q('attachments'))
        index = len(attachments) + 1
        attachment = etree.Element(Q('attachment'), eId=f'att_{index}')
        if attachment.get('eId') in _ids(root): raise Conflict('Schedule identifier collision')
        doc = etree.SubElement(attachment, Q('doc'), name='schedule')
        # A schedule is a separate AKN document context with its own metadata.
        template = attachments.find('./' + Q('attachment') + '/' + Q('doc') + '/' + Q('meta'))
        if template is None: raise Conflict('A schedule metadata template is required')
        meta = deepcopy(template)
        for el in meta.iter():
            for attr in ('value', 'href'):
                v = el.get(attr)
                if v: el.set(attr, re.sub(r'/!schedule_\d+', f'/!schedule_{index}', v))
        doc.append(meta); body = etree.SubElement(doc, Q('mainBody'))
        body.append(fragment(op['fragment']))
        _stamp(root, body, attachment.get('eId'), operation_key, identities)
        identities[attachment.get('eId')] = digest((operation_key + ':attachment').encode())[:24]
        attachments.append(attachment)
    elif action == 'table_insert':
        tables = list(node.iter(Q('table')))
        if len(tables) != 1: raise Conflict('Schedule must have one target table')
        table = tables[0]
        labels = [normalise_num(text(row[0])) for row in table if len(row)]
        group = normalise_num(op['after_group'])
        if labels.count(group) != 1: raise Conflict('Schedule group anchor missing or ambiguous')
        anchor = labels.index(group)
        if any(re.fullmatch('[IVX]+', label) for label in labels[anchor+1:]):
            raise Conflict('Insertion point is not the last schedule group')
        for row in op['rows']:
            tr = etree.Element(Q('tr'))
            for cell in row:
                td = etree.SubElement(tr, Q('td')); etree.SubElement(td, Q('p')).text = cell
            _stamp(root, tr, table.get('eId'), operation_key, identities); table.append(tr)
    else: raise Conflict(f'Unknown action: {action}')
    return {'target_eid': before_id, 'destination_eid':node.get('eId'), 'target_identity': identities.get(node.get('eId')), 'before': before,
            'after': text(node) if node.getparent() is not None else '', **details}


def update_metadata(root, effective_date, applications, modifications=()):
    act = root.find(Q('act')); act.set('contains', 'singleVersion')
    work_uri = act.find('./' + Q('meta') + '/' + Q('identification') + '/' + Q('FRBRWork') + '/' + Q('FRBRuri')).get('value')
    previous_uri = act.find('./' + Q('meta') + '/' + Q('identification') + '/' + Q('FRBRExpression') + '/' + Q('FRBRuri')).get('value')
    # Only live intra-work references follow the new expression. Historical
    # provenance links deliberately retain the date they describe.
    for ref in root.iter(Q('ref')):
        href = ref.get('href', '')
        if href.startswith(work_uri + '/'):
            ref.set('href', re.sub(r'/eng@\d{4}-\d{2}-\d{2}', '/eng@' + effective_date, href))
    def container(parent, name, order, **attrs):
        existing = parent.find(Q(name))
        if existing is not None: return existing
        element = etree.Element(Q(name), **attrs)
        index = next((i for i, el in enumerate(parent) if order.index(tag(el)) > order.index(name)), len(parent))
        parent.insert(index, element)
        return element
    meta_order = ['identification','publication','classification','lifecycle','workflow','analysis','temporalData','references','notes','proprietary','presentation']
    for meta in root.iter(Q('meta')):
        ident = meta.find(Q('identification'))
        if ident is None: continue
        for level in ('FRBRExpression', 'FRBRManifestation'):
            group = ident.find(Q(level))
            for el in group:
                if el.get('value'):
                    el.set('value', re.sub(r'/eng@\d{4}-\d{2}-\d{2}', '/eng@' + effective_date, el.get('value')))
                if tag(el) == 'FRBRdate':
                    el.set('date', effective_date); el.set('name', 'consolidation' if level == 'FRBRExpression' else 'generation')
    meta = act.find(Q('meta'))
    lifecycle = container(meta, 'lifecycle', meta_order, source='#nyayabandhu')
    for application in applications:
        event_id = 'amendment_' + digest(encode(application))[:16]
        references = container(meta, 'references', meta_order, source='#nyayabandhu')
        instrument_id = 'instrument_' + digest(application['work_uri'].encode())[:16]
        if not root.xpath('//*[@eId=$eid]',eid=instrument_id):
            etree.SubElement(references,Q('TLCObject'),eId=instrument_id,href=application['work_uri'],showAs='Amending instrument')
        if not root.xpath('//*[@eId=$eid]',eid=event_id):
            etree.SubElement(lifecycle, Q('eventRef'), eId=event_id, date=application['date'],
                             type='amendment', source='#nyayabandhu', refersTo='#'+instrument_id)
    for item in modifications:
        op, change = item['operation'], item['change']
        if op['action'] == 'effect': continue
        analysis = container(meta, 'analysis', meta_order, source='#nyayabandhu')
        passive = container(analysis, 'passiveModifications', ['activeModifications','passiveModifications','restrictions','judicial','parliamentary','mappings','otherReferences','otherAnalysis'])
        types = {'text_omit':'repeal','omit_provision':'repeal','text_insert':'insertion','insert_provision':'insertion',
                 'schedule_add':'insertion','table_insert':'insertion','renumber':'renumbering','replace_provision':'replacement'}
        mod = etree.SubElement(passive, Q('textualMod'), eId='mod_' + digest(change['operation'].encode())[:16],
                               type=types.get(op['action'], 'substitution'))
        etree.SubElement(mod, Q('source'), href=item['source_uri'] + '#' + op['source']['source_eid'])
        eid = change.get('target_eid')
        # Historical destination remains resolvable in the exported predecessor.
        etree.SubElement(mod, Q('destination'), href=previous_uri + ('#' + eid if eid else ''))


def run(root, operations, identities, tombstones):
    root, identities, tombstones = deepcopy(root), dict(identities), list(tombstones)
    before = etree.tostring(root, encoding='unicode', pretty_print=True)
    changes, conflicts = [], []
    for index, (operation_key, op) in enumerate(operations):
        trial, ids, tombs = deepcopy(root), dict(identities), list(tombstones)
        try:
            for decision in op.get('reference_updates', []):
                resolver = decision.get('resolved_by')
                if not resolver: continue
                later = [candidate for key, candidate in operations[index+1:]
                         if candidate.get('id') == resolver]
                if len(later) != 1 or later[0]['action'] != 'text_omit' or not any(
                    r['eid'] == decision['eid'] and r['href'] == decision['old_href'] and r['text'] == decision['old_text']
                    for r in later[0].get('inline_removals', [])
                ):
                    raise Conflict('Deferred reference decision requires an exact later inline omission in this batch')
            change = apply_one(trial, op, ids, tombs, operation_key)
            root, identities, tombstones = trial, ids, tombs
            changes.append({'operation': operation_key, **change})
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            conflicts.append({'operation': operation_key, 'reason': str(exc)})
            # Remaining instructions may depend on this instruction. Never
            # present a speculative continuation as a valid consolidation.
            break
    report = validate(root)
    after = etree.tostring(root, encoding='unicode', pretty_print=True)
    return root, {'ok': not conflicts and report['ok'], 'conflicts': conflicts,
                  'changes': changes, 'validation': report, 'identities': identities,
                  'tombstones': tombstones, 'diff': '\n'.join(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile='before', tofile='after', lineterm=''))}
