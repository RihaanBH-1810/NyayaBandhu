"""
BBMP Act → Akoma Ntoso XML Generator (v2 — OOP refactor)
Fixes: eId uniqueness, external-ref detection, heading reconstruction,
       chapter headings, definition gaps, preface structure.
"""
import re, os
import xml.etree.ElementTree as ET
from xml.dom import minidom
import pymupdf


# ═══════════════════════════════════════════════════════════════════
#  Text extraction & normalisation
# ═══════════════════════════════════════════════════════════════════

class TextExtractor:
    """Pulls English text from the bilingual gazette PDF."""

    ANCHOR = re.compile(r"(DEPARTMENT\s+OF\s+PARLIAMENTARY\s+AFFAIRS)", re.I)

    def extract(self, pdf_path: str) -> str:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(pdf_path)
        doc = pymupdf.open(pdf_path)
        full, started = "", False
        for pg in range(len(doc)):
            txt = doc.load_page(pg).get_text("text")
            if not started:
                m = self.ANCHOR.search(txt)
                if m:
                    started = True
                    txt = txt[m.start():]
                else:
                    continue
            if started:
                full += txt + "\n"
        return full


class TextNormalizer:
    """Cleans, joins, and reconstructs extracted text."""

    # Known structural‐start patterns (used by line‐joiner)
    # All-caps lines are structural starts (chapter titles, etc.)
    _ALLCAPS = re.compile(r"^[A-Z][A-Z\s,\-\'\(\)]+$")
    _STRUCT = re.compile(
        r"^("
        r"CHAPTER\s|FIRST\s+SCHEDULE|SECOND\s+SCHEDULE|"
        r"\d+\.\s|\(\d+\)\s|\([a-z]\)\s|\([ivxlcdm]+\)\s|"
        r"Provided\s+that|Provided\s+further|Explanation[\.\:\-]|"
        r"THE\s+BRUHAT|An\s+Act\s+to|Whereas|Be\s+it\s+enacted|"
        r"DEPARTMENT\s+OF|NOTIFICATION|"
        r"\(See\s+section|\(A\)\s|\(B\)\s|\(C\)\s"
        r")", re.I)

    _ORPHAN = re.compile(
        r"^(\d+\.|[A-Z]+\.|[IVXLCDM]+\.|\(\d+\)|\([a-z]\)"
        r"|\([IVXLCDM]+\)|[a-z]\.|[ivxlcdm]+\.)$")

    def run(self, raw: str) -> str:
        t = self._clean(raw)
        t = self._stitch_orphans(t)
        t = self._join_hyphens(t)
        t = self._join_continuations(t)
        return t

    # ── internal helpers ──────────────────────────────────────
    def _clean(self, text):
        text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E]+', '', text)
        text = re.sub(r'^.*Part\s*-\s*IVA.*$', '', text, flags=re.M | re.I)
        text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.M)
        return re.sub(r'\n+', '\n', text)

    def _stitch_orphans(self, text):
        lines, out, pending = text.split('\n'), [], ""
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            if self._ORPHAN.match(ln):
                pending += ln + " "
            else:
                out.append((pending + ln) if pending else ln)
                pending = ""
        return '\n'.join(out)

    def _join_hyphens(self, text):
        """Rejoin words split by end‐of‐line hyphens (e.g. 're-\\nconstruction')."""
        return re.sub(r'-\n\s*', '-', text)

    def _join_continuations(self, text):
        lines = text.split('\n')
        joined = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            if not joined:
                joined.append(ln)
            elif self._STRUCT.match(ln):
                joined.append(ln)
            elif self._ALLCAPS.match(ln):
                joined.append(ln)
            else:
                prev = joined[-1]
                if prev.endswith(('.', ';', ':', '-', ',')):
                    joined.append(ln)
                else:
                    joined[-1] = prev + ' ' + ln
        return '\n'.join(joined)


# ═══════════════════════════════════════════════════════════════════
#  Cross‐reference resolver
# ═══════════════════════════════════════════════════════════════════

class ReferenceResolver:
    """Wraps 'section N' in <ref> only when the citation is internal."""

    # External acts commonly cited in the BBMP Act
    EXTERNAL_ACTS = [
        "Indian Penal Code", "Representation of the Peoples Act",
        "Representation of the People Act",
        "Karnataka Stamp Act", "Karnataka Town and Country Planning Act",
        "Karnataka Municipal Corporations Act",
        "Karnataka Societies Registration Act",
        "Oaths Act", "Code of Criminal Procedure",
        "Karnataka Land Revenue Act", "Karnataka Land Reforms Act",
        "Karnataka Education Act", "Karnataka Transparency",
        "Right to Information Act", "Prevention of Corruption Act",
        "Indian Evidence Act", "Karnataka Municipalities Act",
        "Karnataka Panchayat Raj Act", "Transfer of Property Act",
        "Karnataka Lokayukta Act", "Karnataka Civil Services",
        "occupational safety, health and working condition code",
        "Karnataka Appellate Tribunal Act",
    ]

    _REF = re.compile(r"(section\s+\d+[A-Z]?)", re.I)

    def wrap(self, text: str, parent: ET.Element):
        """Add text to *parent*, wrapping internal section refs in <ref>."""
        # Build a lowercase copy for look-behind context checks
        text_lower = text.lower()
        parts = self._REF.split(text)
        if len(parts) == 1:
            parent.text = parts[0]
            return

        parent.text = parts[0]
        cum_len = len(parts[0])
        for i in range(1, len(parts), 2):
            ref_text = parts[i]
            trail = parts[i + 1] if i + 1 < len(parts) else ""
            sec_num = re.search(r"\d+", ref_text).group()

            if self._is_external(text_lower, cum_len):
                # Leave as plain text — no <ref> tag
                if parent.text is None:
                    parent.text = ""
                # Append to tail of last child, or to parent.text
                children = list(parent)
                if children:
                    prev = children[-1]
                    prev.tail = (prev.tail or "") + ref_text + trail
                else:
                    parent.text += ref_text + trail
            else:
                ref_el = ET.SubElement(parent, "ref", href=f"#sec_{sec_num}")
                ref_el.text = ref_text
                ref_el.tail = trail
            cum_len += len(ref_text) + len(trail)

    def _is_external(self, text_lower: str, pos: int) -> bool:
        """True when 'section N' at *pos* refers to an external statute."""
        window = text_lower[max(0, pos - 200): pos + 80]
        # Pattern: "section X of the <ExternalAct>"
        if re.search(r"section\s+\d+\w?\s+of\s+the\s+", window):
            for act in self.EXTERNAL_ACTS:
                if act.lower() in window:
                    return True
        return False


# ═══════════════════════════════════════════════════════════════════
#  Metadata builder
# ═══════════════════════════════════════════════════════════════════

class MetadataBuilder:
    """Constructs the <meta> block (FRBR, publication, lifecycle, etc.)."""

    def build(self, act: ET.Element) -> ET.Element:
        meta = ET.SubElement(act, "meta")
        self._identification(meta)
        self._publication(meta)
        self._lifecycle(meta)
        self._classification(meta)
        self._references(meta)
        return meta

    def _identification(self, meta):
        ident = ET.SubElement(meta, "identification", source="#parser")
        w = ET.SubElement(ident, "FRBRWork")
        ET.SubElement(w, "FRBRthis", value="/akn/in/karnataka/act/2020/bbmp_act/main")
        ET.SubElement(w, "FRBRuri", value="/akn/in/karnataka/act/2020/bbmp_act")
        ET.SubElement(w, "FRBRdate", date="2020-12-19", name="enactment")
        ET.SubElement(w, "FRBRauthor", href="#karnataka_legislature")
        ET.SubElement(w, "FRBRcountry", value="in")
        e = ET.SubElement(ident, "FRBRExpression")
        ET.SubElement(e, "FRBRthis", value="/akn/in/karnataka/act/2020/bbmp_act/eng@2020-12-21/main.xml")
        ET.SubElement(e, "FRBRuri", value="/akn/in/karnataka/act/2020/bbmp_act/eng@2020-12-21")
        ET.SubElement(e, "FRBRdate", date="2020-12-21", name="publication")
        ET.SubElement(e, "FRBRauthor", href="#parser")
        ET.SubElement(e, "FRBRlanguage", language="eng")
        m = ET.SubElement(ident, "FRBRManifestation")
        ET.SubElement(m, "FRBRthis", value="/akn/in/karnataka/act/2020/bbmp_act/eng@2020-12-21/main.xml")
        ET.SubElement(m, "FRBRuri", value="/akn/in/karnataka/act/2020/bbmp_act/eng@2020-12-21/main.xml")
        ET.SubElement(m, "FRBRdate", date="2020-12-21", name="generation")
        ET.SubElement(m, "FRBRauthor", href="#parser")

    def _publication(self, meta):
        ET.SubElement(meta, "publication", date="2020-12-21",
                      name="Karnataka Gazette Extraordinary",
                      showAs="Karnataka Gazette Extraordinary",
                      number="DPAL 20 SHASANA 2020")

    def _lifecycle(self, meta):
        lc = ET.SubElement(meta, "lifecycle", source="#parser")
        ET.SubElement(lc, "eventRef", eId="evt_1", date="2020-12-19",
                      type="generation", source="#karnataka_legislature")
        ET.SubElement(lc, "eventRef", eId="evt_2", date="2020-12-21",
                      type="publication", source="#karnataka_gazette")

    def _classification(self, meta):
        cl = ET.SubElement(meta, "classification", source="#parser")
        for i, (v, s) in enumerate([
            ("municipal governance", "Municipal Governance"),
            ("urban local body", "Urban Local Body"),
            ("bengaluru", "Bengaluru"),
        ], 1):
            ET.SubElement(cl, "keyword", eId=f"kw_{i}", value=v, showAs=s)

    def _references(self, meta):
        refs = ET.SubElement(meta, "references", source="#parser")
        ET.SubElement(refs, "TLCOrganization", eId="karnataka_legislature",
                      href="/akn/in/karnataka", showAs="Karnataka State Legislature")
        ET.SubElement(refs, "TLCOrganization", eId="karnataka_gazette",
                      href="/akn/in/karnataka/gazette", showAs="Karnataka Gazette")
        ET.SubElement(refs, "TLCRole", eId="parser",
                      href="/akn/ontology/role/parser", showAs="Automated Parser")


# ═══════════════════════════════════════════════════════════════════
#  Akoma Ntoso mapper (core engine)
# ═══════════════════════════════════════════════════════════════════

class AkomaMapper:
    """Maps normalised text lines into an Akoma Ntoso XML tree."""

    # ── compiled patterns ────────────────────────────────────
    _CHP = re.compile(r"^CHAPTER\s+([IVXLCDM]+)", re.I)
    _SEC = re.compile(r"^(\d+)\.\s+(.*)")
    _SUBSEC = re.compile(r"^\((\d+)\)\s+(.*)")
    _CLAUSE = re.compile(r"^\(([a-z])\)\s+(.*)")
    _ROMAN = r"(?:x{0,3}(?:ix|iv|v?i{0,3})|vi{1,3}|iv|v)"
    _SUBCLAUSE = re.compile(rf"^\(({_ROMAN})\)\s+(.*)", re.I)
    _PROVISO = re.compile(r"^Provided\s+(?:further\s+)?that[\s,]+(.+)", re.I)
    _EXPLAN = re.compile(r"^Explanation\.?\s*[:\-]?\s*(.*)", re.I)
    _SCHED = re.compile(r"^(FIRST|SECOND|THIRD)\s+SCHEDULE", re.I)
    # Chapter title: all‐caps (allowing spaces, commas, hyphens, apostrophes)
    _CHP_TITLE = re.compile(r"^[A-Z][A-Z\s,\-\'\(\)]+$")

    def __init__(self):
        self.ref = ReferenceResolver()
        self._used_eids: set[str] = set()

    # ── public interface ─────────────────────────────────────

    def map(self, text: str) -> str:
        root = ET.Element("akomaNtoso",
            xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0")
        act = ET.SubElement(root, "act",
            name="TheBruhatBengaluruMahanagaraPalikeAct2020")

        MetadataBuilder().build(act)

        preface = ET.SubElement(act, "preface")
        body = ET.SubElement(act, "body")

        # state
        st = _State(body)
        components = None

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            # ── schedule ──────────────────────────────────────
            m = self._SCHED.match(line)
            if m:
                if components is None:
                    components = ET.SubElement(act, "components")
                name = m.group(1).upper()
                comp = ET.SubElement(components, "component")
                st.schedule = ET.SubElement(comp, "schedule",
                    **self._ids(f"sch_{name.lower()}"))
                ET.SubElement(st.schedule, "num").text = f"{name} SCHEDULE"
                st.reset()
                continue

            if st.schedule is not None:
                c = st.schedule.find("content")
                if c is None:
                    c = ET.SubElement(st.schedule, "content")
                ET.SubElement(c, "p").text = line
                continue

            # ── chapter ───────────────────────────────────────
            m = self._CHP.match(line)
            if m:
                st.in_body = True
                num = m.group(1)
                st.chapter = ET.SubElement(body, "chapter",
                    **self._ids(f"chp_{num}"))
                ET.SubElement(st.chapter, "num").text = num
                # Extract title from remainder of same line if present
                remainder = line[m.end():].strip()
                if remainder:
                    ET.SubElement(st.chapter, "heading").text = remainder
                    st.pending_title = None
                else:
                    st.pending_title = st.chapter
                st.section = st.subsec = st.clause = st.subclause = None
                st.in_defs = False
                continue

            # ── chapter title (one or more all‐caps lines) ────
            if st.pending_title is not None:
                if self._CHP_TITLE.match(line):
                    existing = st.pending_title.find("heading")
                    if existing is not None:
                        existing.text += " " + line
                    else:
                        ET.SubElement(st.pending_title, "heading").text = line
                    continue
                else:
                    # First non-title line: also try mixed-case continuation
                    if line[0].isupper() and not self._SEC.match(line) and not self._SUBSEC.match(line):
                        existing = st.pending_title.find("heading")
                        if existing is not None:
                            existing.text += " " + line
                            st.pending_title = None
                            continue
                    st.pending_title = None

            # ── preface ───────────────────────────────────────
            if not st.in_body:
                ET.SubElement(preface, "p").text = line
                continue

            # ── section ───────────────────────────────────────
            m = self._SEC.match(line)
            if m:
                self._handle_section(m, st)
                continue

            # ── subsection ────────────────────────────────────
            m = self._SUBSEC.match(line)
            if m and st.section is not None:
                self._handle_subsection(m, st)
                continue

            # ── clause / subclause ────────────────────────────
            cm = self._CLAUSE.match(line)
            sm = self._SUBCLAUSE.match(line)
            if cm and sm and st.section is not None:
                if st.clause is not None:
                    cm = None
                else:
                    sm = None
            if cm and st.section is not None:
                self._handle_clause(cm, st)
                continue
            if sm and st.section is not None:
                self._handle_subclause(sm, st)
                continue

            # ── proviso ───────────────────────────────────────
            if self._PROVISO.match(line):
                par = st.innermost()
                if par is not None:
                    blk = ET.SubElement(par, "block", name="proviso")
                    c = ET.SubElement(blk, "content")
                    p = ET.SubElement(c, "p")
                    self.ref.wrap(line, p)
                    continue

            # ── explanation ───────────────────────────────────
            if self._EXPLAN.match(line):
                par = st.innermost()
                if par is not None:
                    blk = ET.SubElement(par, "block", name="explanation")
                    c = ET.SubElement(blk, "content")
                    p = ET.SubElement(c, "p")
                    self.ref.wrap(line, p)
                    continue

            # ── fallback ──────────────────────────────────────
            container = st.innermost() or st.chapter or body
            c = container.find("content")
            if c is None:
                c = ET.SubElement(container, "content")
            p = ET.SubElement(c, "p")
            self.ref.wrap(line, p)

        xml_bytes = ET.tostring(root, encoding='utf-8')
        return minidom.parseString(xml_bytes).toprettyxml(indent="  ")

    # ── element handlers ─────────────────────────────────────

    def _handle_section(self, m, st):
        sec_num, rest = m.group(1), m.group(2)
        parent = st.chapter if st.chapter is not None else st.body
        st.section = ET.SubElement(parent, "section",
            **self._ids(f"sec_{sec_num}"))
        ET.SubElement(st.section, "num").text = f"{sec_num}."

        # Extract heading (text before ".-")
        hm = re.match(r"^(.*?)\.?\s*-\s*(.*)$", rest)
        if hm and hm.group(1).strip():
            ET.SubElement(st.section, "heading").text = hm.group(1).strip()
            rem = hm.group(2).strip()
            if rem:
                # Check if remainder starts with embedded subsection (1)
                sub_m = self._SUBSEC.match(rem)
                if sub_m:
                    # Don't put it in content; return it to be processed
                    st.in_defs = (sec_num == "2")
                    st.subsec = st.clause = st.subclause = None
                    self._handle_subsection(sub_m, st)
                    return
                p = ET.SubElement(ET.SubElement(st.section, "content"), "p")
                self.ref.wrap(rem, p)
        else:
            p = ET.SubElement(ET.SubElement(st.section, "content"), "p")
            self.ref.wrap(rest, p)

        st.in_defs = (sec_num == "2")
        st.subsec = st.clause = st.subclause = None

    def _handle_subsection(self, m, st):
        num, text = m.group(1), m.group(2)
        eid = self._make_child_eid(st.section, "subsec", num)
        st.subsec = ET.SubElement(st.section, "subsection", **self._ids(eid))
        ET.SubElement(st.subsec, "num").text = f"({num})"

        c = ET.SubElement(st.subsec, "content")
        p = ET.SubElement(c, "p")
        if st.in_defs:
            dm = re.match(r'^["\']?([^"\']+?)["\']?\s+(means|includes)\b', text, re.I)
            if dm:
                d = ET.SubElement(p, "def")
                d.text = dm.group(1).strip().strip("\"'")
                d.tail = text[dm.end(1):]
            else:
                self.ref.wrap(text, p)
        else:
            self.ref.wrap(text, p)
        st.clause = st.subclause = None

    def _handle_clause(self, m, st):
        letter, text = m.group(1), m.group(2)
        parent = st.subsec if st.subsec is not None else st.section
        eid = self._make_child_eid(parent, "clause", letter)
        st.clause = ET.SubElement(parent, "clause", **self._ids(eid))
        ET.SubElement(st.clause, "num").text = f"({letter})"
        p = ET.SubElement(ET.SubElement(st.clause, "content"), "p")
        self.ref.wrap(text, p)
        st.subclause = None

    def _handle_subclause(self, m, st):
        num, text = m.group(1).lower(), m.group(2)
        parent = st.clause or st.subsec or st.section
        eid = self._make_child_eid(parent, "subclause", num)
        st.subclause = ET.SubElement(parent, "subclause", **self._ids(eid))
        ET.SubElement(st.subclause, "num").text = f"({num})"
        p = ET.SubElement(ET.SubElement(st.subclause, "content"), "p")
        self.ref.wrap(text, p)

    # ── eId helpers ──────────────────────────────────────────

    def _ids(self, eid: str) -> dict:
        """Return unique eId/wId pair, deduplicating if needed."""
        unique = eid
        counter = 2
        while unique in self._used_eids:
            unique = f"{eid}__{counter}"
            counter += 1
        self._used_eids.add(unique)
        return {"eId": unique, "wId": unique}

    def _make_child_eid(self, parent, kind, num):
        pid = parent.get("eId") if parent is not None else "body"
        return f"{pid}-{kind}_{num}"


class _State:
    """Mutable parsing state passed between handler methods."""
    def __init__(self, body):
        self.body = body
        self.in_body = False
        self.chapter = None
        self.section = None
        self.subsec = None
        self.clause = None
        self.subclause = None
        self.schedule = None
        self.pending_title = None
        self.in_defs = False

    def reset(self):
        self.chapter = self.section = self.subsec = None
        self.clause = self.subclause = None
        self.in_defs = False

    def innermost(self):
        return (self.subclause or self.clause
                or self.subsec or self.section)


# ═══════════════════════════════════════════════════════════════════
#  Orchestrator
# ═══════════════════════════════════════════════════════════════════

class ActParser:
    """End-to-end pipeline: PDF → cleaned text → Akoma Ntoso XML."""

    def __init__(self, pdf_path: str, output_path: str):
        self.pdf_path = pdf_path
        self.output_path = output_path

    def run(self):
        print(f"  [1/4] Extracting text from {self.pdf_path}...")
        raw = TextExtractor().extract(self.pdf_path)

        print("  [2/4] Normalising text...")
        text = TextNormalizer().run(raw)

        # Debug dump
        dbg = os.path.splitext(self.output_path)[0] + "_extracted.txt"
        with open(dbg, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"         (intermediate text → {dbg})")

        print("  [3/4] Mapping to Akoma Ntoso...")
        xml = AkomaMapper().map(text)

        print(f"  [4/4] Writing XML → {self.output_path}")
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(xml)

        print("  ✔ Done.\n")


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

import argparse, glob

# Map of document type → subdirectory under data/
DOC_TYPE_DIRS = {
    "base_act":   "v0s",
    "amendment":  "amendments",
}

LANG_CHOICES = ["eng", "kan", "kan_eng"]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="akn-parser",
        description="Convert legislative PDF(s) to Akoma Ntoso XML.",
    )
    p.add_argument(
        "-t", "--type",
        choices=list(DOC_TYPE_DIRS.keys()),
        required=True,
        dest="doc_type",
        help="Type of document to process (base_act | amendment).",
    )
    p.add_argument(
        "-l", "--lang",
        choices=LANG_CHOICES,
        required=True,
        help="Language variant (eng | kan | kan_eng). "
             "Determines the subfolder under data/{type}/.",
    )
    p.add_argument(
        "-n", "--count",
        type=int,
        default=0,
        help="Number of PDFs to process (0 = all, default: all).",
    )
    return p


def _collect_pdfs(doc_type: str, lang: str) -> list[str]:
    """Return a sorted list of PDF paths for the given type + language."""
    subdir = DOC_TYPE_DIRS[doc_type]
    pdf_dir = os.path.join(REPO_ROOT, "data", subdir, lang)
    if not os.path.isdir(pdf_dir):
        raise SystemExit(
            f"Error: PDF directory does not exist: {pdf_dir}\n"
            f"Expected structure: data/{subdir}/{lang}/*.pdf"
        )
    pdfs = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))
    if not pdfs:
        raise SystemExit(f"Error: No PDF files found in {pdf_dir}")
    return pdfs


def main():
    args = _build_parser().parse_args()

    pdfs = _collect_pdfs(args.doc_type, args.lang)

    # Limit count (0 means all)
    if args.count > 0:
        pdfs = pdfs[: args.count]

    # Output directory: out/{doc_type}/{lang}/
    out_dir = os.path.join(REPO_ROOT, "out", args.doc_type, args.lang)
    os.makedirs(out_dir, exist_ok=True)

    total = len(pdfs)
    print(f"Processing {total} PDF(s)  "
          f"[type={args.doc_type}, lang={args.lang}]\n")

    for idx, pdf_path in enumerate(pdfs, 1):
        basename = os.path.splitext(os.path.basename(pdf_path))[0]
        out_path = os.path.join(out_dir, f"{basename}.xml")

        print(f"[{idx}/{total}] {os.path.basename(pdf_path)}")
        ActParser(pdf_path, out_path).run()

    print(f"All done — {total} file(s) written to {out_dir}")


if __name__ == "__main__":
    main()