from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from lxml import etree
from akn_parser.render import AKN_NS
from akn_parser.pipeline import DEFAULT_SCHEMA
from akn_parser.validate import Validator

NS = {'a': AKN_NS}
Q = lambda tag: f'{{{AKN_NS}}}{tag}'


class Conflict(ValueError):
    """A precondition no longer holds."""


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Expected an ISO date YYYY-MM-DD')
    return value


def parse(raw):
    try:
        root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    except etree.XMLSyntaxError as exc:
        raise ValueError('Invalid XML: ' + str(exc)) from exc
    if root.getroottree().docinfo.doctype:
        raise ValueError('DTD declarations are not accepted')
    return root


def serialise(root):
    return etree.tostring(root, encoding='utf-8', xml_declaration=True)


def canonical_hash(root):
    return digest(etree.tostring(root, method='c14n'))


def tag(node):
    return etree.QName(node).localname if isinstance(node.tag, str) else ''


def text(node):
    return re.sub(r'\s+', ' ', ''.join(node.itertext())).strip()


def metadata(root):
    def value(path, attr):
        values = root.xpath('./a:act/a:meta/a:identification/' + path + '/@' + attr, namespaces=NS)
        return values[0] if values else ''
    return {'work_uri': value('a:FRBRWork/a:FRBRuri', 'value'),
            'publication_date': value('a:FRBRExpression/a:FRBRdate', 'date'),
            'language': value('a:FRBRExpression/a:FRBRlanguage', 'language')}


def validate(root):
    report = Validator(DEFAULT_SCHEMA).check(root, 'eng')
    return {'ok': report.ok and report.schema_valid is True, 'summary': report.summary(),
            'schema_errors': report.schema_errors, 'duplicate_eids': report.duplicate_eids,
            'malformed_eids': report.malformed_eids, 'dangling_refs': report.dangling_refs,
            'foreign_residue': report.foreign_residue}
