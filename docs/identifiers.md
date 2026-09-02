# Identifiers and metadata

`eId` construction, FRBR URIs, and the metadata block.

Normative source:
[Akoma Ntoso Naming Convention v1.0](https://docs.oasis-open.org/legaldocml/akn-nc/v1.0/akn-nc-v1.0.html).

## eId grammar

```
eId       ::= component ( "__" component )*
component ::= element_ref [ "_" number ]
```

Levels are separated by a **double** underscore; an element abbreviation is
separated from its number by a **single** underscore.

```
sec_7
sec_7__subsec_1
sec_7__subsec_1__proviso_4
sec_2__cl_a__content__p_1
chp_IV__sec_19__subsec_1__proviso_2__cl_k__subcl_ii
att_1__hcontainer_1__table_1__tr_19__td_2
```

## Element abbreviations

The naming convention fixes abbreviations for these elements. Any element not
listed uses its full name.

| Element | `element_ref` | Element | `element_ref` |
| --- | --- | --- | --- |
| `alinea` | `al` | `paragraph` | `para` |
| `article` | `art` | `quotedStructure` | `qstr` |
| `attachment` | `att` | `quotedText` | `qtext` |
| `blockList` | `list` | `recital` | `rec` |
| `chapter` | `chp` | `recitals` | `recs` |
| `citation` | `cit` | `section` | `sec` |
| `citations` | `cits` | `subchapter` | `subchp` |
| `clause` | `cl` | `subclause` | `subcl` |
| `component` | `cmp` | `subdivision` | `subdvs` |
| `components` | `cmpnts` | `subparagraph` | `subpara` |
| `componentRef` | `cref` | `subsection` | `subsec` |
| `division` | `dvs` | `temporalGroup` | `tmpg` |
| `documentRef` | `dref` | `wrapUp` | `wrapup` |
| `eventRef` | `eref` | `mainBody`, `body` | `body` |

Elements emitted by this parser that keep their full name: `proviso`, `point`,
`indent`, `hcontainer`, `part`, `content`, `intro`, `subheading`, `table`,
`tr`, `th`, `td`, `p`, `ref`, `def`, `omissis`, `formula`, `longTitle`,
`crossHeading`.

The mapping lives in `ELEMENT_REF` in `akn_parser/eids.py`.

## Number normalisation

The number part is the text of `<num>` with edge punctuation removed, internal
whitespace deleted, and remaining separators reduced to `-`. Case is preserved.

| `<num>` | Number part |
| --- | --- |
| `(1)` | `1` |
| `1.` | `1` |
| `(a)` | `a` |
| `(iv)` | `iv` |
| `12A.` | `12A` |
| `Art. 11.2 bis` | `11-2bis` |

A leading `-` is meaningful and preserved: an article inserted before article 1
gives `art_-1`.

## Unnumbered elements

An element with no `<num>` is counted within its parent, using Arabic numerals:

```
sec_7__subsec_1__proviso_1
sec_7__subsec_1__proviso_2
sec_7__subsec_1__proviso_3
```

Counters restart in each parent, so section 6 and section 7 both have a
`proviso_1`.

Elements that are unique within their parent take no number at all:

```
sec_2__intro
sec_2__cl_a__content
att_1__hcontainer_1__subheading
```

## Attachments

A schedule sits in a `<doc>` inside an `<attachment>`. The naming convention
treats a document element as a fresh numbering context, so counters restart
there, but identifiers keep the attachment's `eId` as their prefix — the
convention's own example is `doc_1__body` "in case of a composite document".

```
att_1
att_1__body
att_1__hcontainer_1
att_1__hcontainer_1__table_1
```

This also satisfies the schema, whose uniqueness constraint on `<act>` selects
every descendant, attachments included:

```xml
<xsd:unique name="eId-act">
  <xsd:selector xpath=".//*"/>
  <xsd:field xpath="@eId"/>
</xsd:unique>
```

## Uniqueness

Identifiers are unique by construction: they are derived from position in the
tree, and no two elements occupy the same position. A collision therefore
indicates that the parsed hierarchy is wrong, and `EIdAssigner` raises
`DuplicateEId` naming both elements rather than disambiguating with a suffix.

See [troubleshooting.md](troubleshooting.md#duplicateeid).

## wId

`wId` is not emitted.

The naming convention specifies that Work-level and Expression-level
identifiers are written separately only when they differ, which happens when an
expression renumbers relative to the *master expression*. The Kannada and
English expressions of these Acts have identical structure, so `wId` would
equal `eId` for every element either way, and omitting it is correct today.

Which expression is the master is a question this parser does not answer.
Karnataka Acts are enacted in Kannada, but Article 348(3) of the Constitution
provides that an English translation published under the Governor's authority
"shall be deemed to be the authoritative text thereof in the English
language" — so the English text is not a mere derivative, and India does not
apply the equal-authenticity rule the way Canada, Switzerland and the EU do.
The choice should be settled by legal advice before any expression renumbers
provisions, because at that point `wId` becomes necessary and must carry the
master expression's identifiers.

See [languages.md](languages.md#how-other-jurisdictions-model-this).

## FRBR URIs

Shape follows Naming Convention §4:

```
/akn/{country}/{doctype}/{date}/{number}
```

For the Karnataka State Civil Services (Regulation of Transfer of Teachers)
Act, 2020:

| Level | URI |
| --- | --- |
| Work | `/akn/in-ka/act/2020-03-26/4` |
| Work component | `/akn/in-ka/act/2020-03-26/4/!main` |
| Expression | `/akn/in-ka/act/2020-03-26/4/eng@2020-03-27` |
| Expression component | `/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main` |
| Manifestation | `/akn/in-ka/act/2020-03-26/4/eng@2020-03-27.xml` |
| Manifestation component | `/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main.xml` |
| Schedule component | `/akn/in-ka/act/2020-03-26/4/!schedule_1` |

Rules:

- The country component is an ISO 3166-1 or 3166-2 code, lowercased. Karnataka
  is `in-ka`. It must equal the value of `<FRBRcountry>`.
- The date in a **Work** URI is the full date the Work came into being — for an
  Act, the date of assent.
- The date in an **Expression** URI is that expression's own date, after `@`.
  For a translation, its date of first publication.
- Components are introduced by `/!`.

Jurisdiction codes are listed in `JURISDICTIONS` in `akn_parser/meta.py`.

## The metadata block

```xml
<meta>
  <identification source="#nyayabandhu">
    <FRBRWork>
      <FRBRthis value="/akn/in-ka/act/2020-03-26/4/!main"/>
      <FRBRuri value="/akn/in-ka/act/2020-03-26/4"/>
      <FRBRalias name="title" value="THE KARNATAKA STATE CIVIL SERVICES …"/>
      <FRBRalias name="title" xml:lang="kn-Latn-x-nudi"
                 value="PÀ£ÁðlPÀ gÁdå ¹«¯ï ¸ÉÃªÉUÀ¼ÀÄ …"/>
      <FRBRdate date="2020-03-26" name="assent"/>
      <FRBRauthor href="#karnatakaLegislature"/>
      <FRBRcountry value="in-ka"/>
      <FRBRnumber value="4"/>
    </FRBRWork>
    <FRBRExpression>
      <FRBRthis value="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main"/>
      <FRBRuri value="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27"/>
      <FRBRdate date="2020-03-27" name="publication"/>
      <FRBRauthor href="#karnatakaLegislature"/>
      <FRBRlanguage language="eng"/>
    </FRBRExpression>
    <FRBRManifestation>
      <FRBRthis value="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main.xml"/>
      <FRBRuri value="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27.xml"/>
      <FRBRdate date="2026-09-01" name="generation"/>
      <FRBRauthor href="#nyayabandhu"/>
      <FRBRformat value="xml"/>
    </FRBRManifestation>
  </identification>
  <publication date="2020-03-27" name="Karnataka Gazette Extra-ordinary"
               showAs="Karnataka Gazette Extra-ordinary"/>
  <classification source="#nyayabandhu">…</classification>
  <lifecycle source="#nyayabandhu">
    <eventRef eId="eref_1" date="2020-03-26" type="generation"
              source="#karnatakaLegislature"/>
  </lifecycle>
  <references source="#nyayabandhu">
    <TLCOrganization eId="karnatakaLegislature"
                     href="/akn/ontology/organization/in-ka/legislature"
                     showAs="Karnataka State Legislature"/>
    <TLCOrganization eId="karnatakaGazette" … />
    <TLCRole eId="nyayabandhu" href="/akn/ontology/role/editor"
             showAs="NyayaBandhu automated parser"/>
    <TLCTerm eId="appointment" … />
  </references>
</meta>
```

## Extracted metadata

These fields are read from the gazette's own front matter:

| Field | Source text |
| --- | --- |
| `number`, `year`, `jurisdiction` | `KARNATAKA ACT NO. 04 OF 2020` |
| `work_date` | `(Received the assent of the Governor on the 26th day of March, 2020)` |
| `expression_date`, `gazette` | `(First Published in the Karnataka Gazette Extra-ordinary on the 27th day of March, 2020)` |
| `title` | `THE KARNATAKA STATE CIVIL SERVICES … ACT, 2020` |
| `notification` | `No. DPAL 12 SHASANA 2020` |
| `manifestation_date` | The date the file was generated |
| `source_title` | The Act's title in the enacting language, from `Ordered that the translation of <title> in the English language` |

## Metadata overrides

`config/documents.json` supplies or replaces any field of `DocumentMeta`,
keyed by the source PDF's file name with or without the `.pdf` extension.
Overrides are applied last, so they win over extracted values.

```json
{
  "tranfer_of_teachers": {
    "keywords": ["Education", "Teacher transfers", "State civil services"],
    "manifestation_date": "2020-03-27"
  }
}
```

Keys beginning with `_` are ignored, so `_comment` can be used for notes.

Overridable fields are the attributes of `DocumentMeta` in
`akn_parser/meta.py`:

| Field | Default |
| --- | --- |
| `jurisdiction` | `in-ka` |
| `doc_type` | `act` |
| `number`, `year` | extracted |
| `work_date`, `expression_date` | extracted |
| `manifestation_date` | today's date |
| `language` | from `--lang` |
| `title`, `gazette`, `notification` | extracted |
| `author_id`, `author_name` | `karnatakaLegislature`, `Karnataka State Legislature` |
| `publisher_id`, `publisher_name` | `karnatakaGazette`, `Karnataka Gazette` |
| `editor_id`, `editor_name` | `nyayabandhu`, `NyayaBandhu automated parser` |
| `keywords` | empty |
| `source_title` | extracted; a 4-tuple of (text, language, encoding, font encoding) |

Setting `manifestation_date` pins the one clock-dependent value in the output,
making a run byte-reproducible.
