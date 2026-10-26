"""Server-side visual AKN editor. Operations are keyed by provision eId."""
from __future__ import annotations

import re
from lxml import etree
from akn_parser.render import AKN_NS

Q = lambda tag: f"{{{AKN_NS}}}{tag}"
MODE = "visual"
TYPES = {"section": "sec", "subsection": "subsec", "clause": "cl", "proviso": "proviso"}
TEXT_ONLY = {"hcontainer"}
CHILDREN = {"body": {"section"}, "chapter": {"section"},
            "section": {"subsection", "clause", "proviso"},
            "subsection": {"clause", "proviso"}, "proviso": {"clause"}}


def _tag(node):
    return etree.QName(node).localname


def _path(node, descendant):
    parts = []
    while descendant is not node:
        parent = descendant.getparent()
        if parent is None:
            raise ValueError("Field is outside selected provision")
        parts.append(parent.index(descendant))
        descendant = parent
    return list(reversed(parts))


def _locate(node, path):
    current = node
    for index in path:
        if not isinstance(index, int) or index < 0 or index >= len(current):
            raise ValueError("Text field no longer exists; reload")
        current = current[index]
    return current


def _field(owner, el):
    return {"owner_eid": owner.get("eId"), "eid": el.get("eId"),
            "path": _path(owner, el), "tag": _tag(el),
            "segments": [el.text or ""] + [child.tail or "" for child in el],
            "protected": [f"{_tag(child)}: {''.join(child.itertext())}" for child in el]}


def prepare(node):
    if _tag(node) not in TYPES.keys() | TEXT_ONLY:
        return {"mode": "visual", "enabled": False, "reason": "Choose a section, subsection, clause or proviso"}
    fields = [_field(node, el) for el in node.iter() if _tag(el) in {"heading", "p"}]
    parent = node.getparent()
    allowed_add = sorted(CHILDREN.get(_tag(node), set()) | ({"section"} if _tag(node) == "section" else set()))
    return {"mode": "visual", "enabled": True, "fields": fields,
            "tag": _tag(node), "eid": node.get("eId"), "number": node.findtext(Q("num")) or "",
            "actions": ["text"] if _tag(node) in TEXT_ONLY else ["text", "add", "remove", "renumber", "move"],
            "add_types": allowed_add,
            "can_move": parent is not None and _tag(parent) in CHILDREN}


def _update_text(node, fields):
    if not isinstance(fields, list) or not fields:
        raise ValueError("No text fields were submitted")
    for field in fields:
        if field.get("owner_eid") != node.get("eId"):
            raise ValueError("Text operation belongs to another provision")
        el = _locate(node, field.get("path", []))
        if field.get("eid") != el.get("eId") or _tag(el) != field.get("tag") or _tag(el) not in {"heading", "p"}:
            raise ValueError("Text field changed; reload")
        segments = field.get("segments")
        if not isinstance(segments, list) or len(segments) != len(el) + 1 or any(not isinstance(x, str) for x in segments):
            raise ValueError("Protected inline elements cannot be removed or edited")
        el.text = segments[0]
        for child, text in zip(el, segments[1:]):
            child.tail = text


def _all_ids(node):
    return {e.get("eId") for e in node.iter() if e.get("eId")}


def _check_incoming(root, node):
    ids = _all_ids(node)
    for ref in root.iter(Q("ref")):
        fragment = ref.get("href", "").split("#")[-1]
        if fragment in ids:
            raise ValueError(f"Cannot change {node.get('eId')}: reference {ref.get('href')} targets this provision or a child")


def _rename(root, node, new_eid):
    old = node.get("eId")
    if not old:
        raise ValueError("Provision has no eId")
    if old == new_eid:
        return
    _check_incoming(root, node)
    descendants = list(node.iter())
    updates = {}
    for el in descendants:
        eid = el.get("eId")
        if eid:
            if not (eid == old or eid.startswith(old + "__")):
                raise ValueError(f"Unexpected child identifier {eid}; cannot rebuild safely")
            updates[eid] = new_eid + eid[len(old):]
    other_ids = {el.get("eId") for el in root.iter() if el not in descendants and el.get("eId")}
    if set(updates.values()) & other_ids:
        raise ValueError("New identifier collides with an existing provision")
    for el in descendants:
        if el.get("eId"):
            el.set("eId", updates[el.get("eId")])


def _number(node, value):
    tag = _tag(node)
    if tag == "proviso":
        raise ValueError("Provisos have no printed number")
    if tag in {"section", "subsection"}:
        if not re.fullmatch(r"[1-9][0-9]*", value):
            raise ValueError("Use a positive Arabic number")
        return f"{value}." if tag == "section" else f"({value})", value
    if not re.fullmatch(r"[a-z]+", value):
        raise ValueError("Use lowercase letters for this clause")
    return f"({value})", value


def _new_id(node, token):
    parent = node.getparent()
    prefix = parent.get("eId") + "__" if parent is not None and parent.get("eId") else ""
    return f"{prefix}{TYPES[_tag(node)]}_{token}"


def _renumber(root, node, value):
    printed, token = _number(node, value)
    num = node.find(Q("num"))
    if num is None:
        raise ValueError("Provision has no number")
    _rename(root, node, _new_id(node, token))
    num.text = printed


def _add(root, parent, child_type):
    if child_type == "section" and _tag(parent) == "section":
        siblings = [c for c in parent.getparent() if _tag(c) == "section"]
        numbers = [int(m.group(1)) for c in siblings if (m := re.fullmatch(r"(\d+)\.", c.findtext(Q("num")) or ""))]
        token = str(max(numbers, default=0) + 1)
        eid = _new_id(parent, token)
        if root.xpath("//*[@eId=$eid]", eid=eid):
            raise ValueError(f"Identifier {eid} already exists")
        new = etree.Element(Q("section")); new.set("eId", eid)
        etree.SubElement(new, Q("num")).text = token + "."
        etree.SubElement(new, Q("heading")).text = "New section"
        content = etree.SubElement(new, Q("content")); content.set("eId", eid + "__content")
        p = etree.SubElement(content, Q("p")); p.set("eId", eid + "__content__p_1"); p.text = "[Enter provision text]"
        parent.getparent().insert(parent.getparent().index(parent) + 1, new)
        return eid
    if child_type not in CHILDREN.get(_tag(parent), set()):
        raise ValueError(f"Cannot add {child_type} inside {_tag(parent)}")
    if _tag(parent) not in {"section", "subsection", "proviso"}:
        raise ValueError("Select a provision to add a child")
    # AKN uses content for a leaf and intro before child provisions. Retain
    # every text and inline node while changing the container and its eIds.
    content = parent.find(Q("content"))
    if content is not None:
        _rename(root, content, parent.get("eId") + "__intro")
        content.tag = Q("intro")
    existing = [c for c in parent if _tag(c) == child_type]
    prefix = parent.get("eId") + "__"
    if child_type == "proviso":
        tokens = [int(m.group(1)) for c in existing if (m := re.search(r"__proviso_(\d+)$", c.get("eId", "")))]
        token = str(max(tokens, default=0) + 1)
    elif child_type == "clause":
        tokens = [c.findtext(Q("num")) or "" for c in existing]
        letters = [s.strip("()") for s in tokens if re.fullmatch(r"\([a-z]\)", s)]
        if len(letters) != len(tokens):
            raise ValueError("Clause numbering is not a simple a-z sequence")
        next_ord = max((ord(x) for x in letters), default=ord("a") - 1) + 1
        if next_ord > ord("z"):
            raise ValueError("Clause numbering past z is not supported")
        token = chr(next_ord)
    else:
        nums = [int(m.group(1)) for c in existing if (m := re.search(r"__(?:subsec)_(\d+)$", c.get("eId", "")))]
        token = str(max(nums, default=0) + 1)
    eid = prefix + TYPES[child_type] + "_" + token
    if root.xpath("//*[@eId=$eid]", eid=eid):
        raise ValueError(f"Identifier {eid} already exists")
    new = etree.Element(Q(child_type))
    new.set("eId", eid)
    if child_type != "proviso":
        etree.SubElement(new, Q("num")).text = f"{token}." if child_type == "section" else f"({token})"
    content = etree.SubElement(new, Q("content")); content.set("eId", eid + "__content")
    p = etree.SubElement(content, Q("p")); p.set("eId", eid + "__content__p_1"); p.text = "[Enter provision text]"
    index = parent.index(existing[-1]) + 1 if existing else len(parent)
    parent.insert(index, new)
    return eid


def edit(root, node, payload):
    action = payload.get("action")
    if _tag(node) in TEXT_ONLY and action != "text":
        raise ValueError("This container supports wording edits only; table structure is fixed")
    if action == "text":
        _update_text(node, payload.get("fields"))
        return f"Edited text in {node.get('eId')}"
    if action == "add":
        eid = _add(root, node, payload.get("child_type"))
        return f"Added {eid}"
    if action == "remove":
        _check_incoming(root, node)
        node.getparent().remove(node)
        return f"Removed {node.get('eId')}"
    if action == "renumber":
        _renumber(root, node, str(payload.get("number", "")).strip())
        return f"Renumbered {node.get('eId')}"
    if action == "move":
        direction = payload.get("direction")
        if direction not in {"up", "down"}:
            raise ValueError("Choose up or down")
        parent = node.getparent()
        siblings = [c for c in parent if _tag(c) == _tag(node)]
        index = siblings.index(node)
        other_index = index + (-1 if direction == "up" else 1)
        if other_index < 0 or other_index >= len(siblings):
            raise ValueError("No provision in that direction")
        other = siblings[other_index]
        # Their printed numbers and identifiers follow their slots, while
        # their content changes places. Incoming references make this unsafe.
        _check_incoming(root, node); _check_incoming(root, other)
        a_id, b_id = node.get("eId"), other.get("eId")
        a_num = node.findtext(Q("num")); b_num = other.findtext(Q("num"))
        if a_num is None or b_num is None:
            raise ValueError("Move requires numbered provisions")
        _rename(root, node, "temporary_move_1")
        _rename(root, other, a_id)
        _rename(root, node, b_id)
        node.find(Q("num")).text = b_num
        other.find(Q("num")).text = a_num
        p = parent; i, j = p.index(node), p.index(other)
        p.remove(node); p.remove(other)
        if i < j:
            p.insert(i, other); p.insert(j, node)
        else:
            p.insert(j, node); p.insert(i, other)
        return f"Moved {a_id} {direction}"
    raise ValueError("Unknown edit operation")
