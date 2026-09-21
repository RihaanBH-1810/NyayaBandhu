"""End-to-end pipeline: PDF -> Akoma Ntoso 3.0 XML."""
from __future__ import annotations

import dataclasses
import os

from . import language
from .eids import EIdAssigner
from .extract import FOREIGN_TAG, TextExtractor
from .meta import MetadataExtractor
from .normalize import TextNormalizer
from .refs import CitationResolver
from .render import AknRenderer, serialise
from .structure import Tokenizer, TreeBuilder
from .validate import ValidationReport, Validator

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SCHEMA = os.path.join(REPO_ROOT, "schemas", "akomantoso30.xsd")
DEFAULT_OVERRIDES = os.path.join(REPO_ROOT, "config", "documents.json")


@dataclasses.dataclass
class ParseResult:
    """Everything one call to :meth:`ActParser.parse` produces.

    ``document`` and ``meta`` are the intermediate :class:`ActDocument` and
    :class:`~akn_parser.meta.DocumentMeta`, kept around for callers that want
    to inspect the parse rather than only the serialised ``xml``.
    """
    xml: bytes
    text: str
    document: object
    meta: object
    report: ValidationReport
    pages: list
    redactions: int


class ActParser:
    """Convert one legislative PDF into a validated Akoma Ntoso document."""

    def __init__(
        self,
        target_lang: str = language.ENGLISH,
        foreign_policy: str = FOREIGN_TAG,
        schema_path: str = DEFAULT_SCHEMA,
        overrides_path: str = DEFAULT_OVERRIDES,
        validate: bool = True,
        keywords: list = (),
    ):
        self.target_lang = target_lang
        self.foreign_policy = foreign_policy
        self.keywords = list(keywords)
        self.validator = Validator(schema_path if validate else "")
        self.metadata = MetadataExtractor(overrides_path)

    def parse(self, pdf_path: str) -> ParseResult:
        """Run the full pipeline on one PDF and return a :class:`ParseResult`.

        The nine stages run in the fixed order described in
        ``docs/architecture.md``: extraction, normalisation, tokenising, tree
        building, identifier assignment, metadata, citation resolution,
        rendering, validation. Identifiers must exist before citations can be
        resolved against them, and the body is rendered before ``<meta>`` so
        that terms discovered while rendering it can be declared there.
        """
        extraction = TextExtractor(
            target_lang=self.target_lang, foreign_policy=self.foreign_policy
        ).extract(pdf_path)

        text = TextNormalizer().run(extraction.text)
        tokens = Tokenizer().tokenize(text)
        document = TreeBuilder().build(tokens)

        eid_index = EIdAssigner().assign(document)

        meta = self.metadata.build(document, pdf_path, self.target_lang)
        if self.keywords and not meta.keywords:
            meta.keywords = self.keywords

        resolver = CitationResolver(
            eid_index, [s.eid for s in document.schedules if s.eid]
        )
        root = AknRenderer(meta, resolver).render(document)
        report = self.validator.check(root, self.target_lang, resolver)

        return ParseResult(
            xml=serialise(root),
            text=text,
            document=document,
            meta=meta,
            report=report,
            pages=extraction.pages,
            redactions=extraction.redactions,
        )
