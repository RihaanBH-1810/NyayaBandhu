# Akoma Ntoso mapping reference

How the structure of an Indian gazette Act maps onto Akoma Ntoso 3.0 elements.

Normative sources:

- [Akoma Ntoso v1.0 Part 1: XML Vocabulary](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part1-vocabulary.html)
- [Akoma Ntoso v1.0 Part 2: Specifications](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part2-specs/) — `schemas/akomantoso30.xsd` is taken from here unmodified

All output is validated against that schema.

## Document skeleton

```xml
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act name="act" contains="originalVersion">
    <meta>…</meta>
    <preface>…</preface>
    <preamble>…</preamble>
    <body>…</body>
    <conclusions>…</conclusions>
    <attachments>…</attachments>
  </act>
</akomaNtoso>
```

`<meta>` children must appear in this order, and optional elements may be
absent but not reordered:

```
identification, publication, classification, lifecycle, workflow,
analysis, temporalData, references, notes, proprietary, presentation
```

## Front matter

| Gazette text | Element |
| --- | --- |
| Notification, act number, gazette citation, assent note | `<preface><p>` |
| `An Act to provide for …` | `<preface><longTitle><p>` |
| `Whereas it is expedient …` | `<preamble><recitals><recital><p>` |
| `Be it enacted by the … Legislature …` | `<preamble><formula name="enactingFormula"><p>` |
| Governor's signature, countersignature, publication formula | `<conclusions><p>` |

```xml
<preface eId="preface">
  <p eId="preface__p_2">KARNATAKA ACT NO. 04 OF 2020</p>
  <longTitle eId="preface__longTitle_1">
    <p eId="preface__longTitle_1__p_1">An Act to provide for regulation of transfer
      of teachers …</p>
  </longTitle>
</preface>
<preamble eId="preamble">
  <recitals eId="preamble__recitals_1">
    <recital eId="preamble__recitals_1__rec_1">
      <p eId="preamble__recitals_1__rec_1__p_1">Whereas it is expedient …</p>
    </recital>
  </recitals>
  <formula eId="preamble__formula_1" name="enactingFormula">
    <p eId="preamble__formula_1__p_1">Be it enacted by the Karnataka State
      Legislature in the seventy first year of the Republic of India, as follows:-</p>
  </formula>
</preamble>
```

## Hierarchy

| Gazette unit | Element | eId prefix |
| --- | --- | --- |
| `CHAPTER IV` | `<chapter>` | `chp` |
| `PART II` | `<part>` | `part` |
| `7. Transfer by counselling.-` | `<section>` | `sec` |
| `(1)` | `<subsection>` | `subsec` |
| `(a)` or `(i)`, one level below a section or subsection | `<clause>` | `cl` |
| `(i)`, one level below a clause | `<subclause>` | `subcl` |
| a further level down | `<point>` | `point` |
| a further level again | `<indent>` | `indent` |
| `Provided that …` | `<proviso>` | `proviso` |
| `Explanation.-` | `<hcontainer name="explanation">` | `hcontainer` |
| `SCHEDULE` | `<attachment><doc name="schedule">` | `att` |

The element for a numbered item is determined by its **parent**, not by whether
its enumerator is a letter or a numeral:

| Parent | Child element |
| --- | --- |
| `body`, `chapter`, `part` | `section` |
| `section`, `subsection`, `proviso` | `clause` |
| `clause` | `subclause` |
| `subclause` | `point` |
| `point` | `indent` |

Indian drafting nests further than Akoma Ntoso provides "sub-" names for. BBMP
s.83(2)(b)(iii) opens a fresh `(a)`–`(d)` list four levels down; `point` and
`indent` carry those levels.

## Content model: `<content>` versus `<intro>`

A hierarchical element contains **either**

```
num?, heading?, subheading?, content
```

**or**

```
num?, heading?, subheading?, intro?, (child provisions)*, wrapUp?
```

The two are mutually exclusive. A `<content>` followed by child provisions is
invalid. Text that introduces sub-provisions therefore goes in `<intro>`, and
only leaf provisions get `<content>`:

```xml
<section eId="sec_2">
  <num>2.</num>
  <heading>Definitions</heading>
  <intro eId="sec_2__intro">
    <p eId="sec_2__intro__p_1">In this Act, unless the context otherwise requires,-</p>
  </intro>
  <clause eId="sec_2__cl_a">
    <num>(a)</num>
    <content eId="sec_2__cl_a__content">
      <p eId="sec_2__cl_a__content__p_1">…</p>
    </content>
  </clause>
</section>
```

Text that appears *after* a provision's children is emitted as `<wrapUp>`.

## Section headings

Indian drafting separates a section heading from its text with `.-` or `.—`:

```
7. Transfer by counselling.-(1) The transfer of teachers under sections 4, 5 …
```

becomes

```xml
<section eId="sec_7">
  <num>7.</num>
  <heading>Transfer by counselling</heading>
  <subsection eId="sec_7__subsec_1">…</subsection>
</section>
```

The heading match is non-greedy and stops at the first `.` followed by a dash,
so hyphenated words inside a heading survive (`Compulsory appointment of a
teacher to Zone-C`). A candidate heading longer than 20 words is rejected as a
sentence rather than a heading.

## Provisos

`<proviso>` is a hierarchical element in its own right. A proviso attaches to
the nearest enclosing section or subsection, never to the list item that
precedes it. Provisos are numbered within their parent, which matches how
legislative text refers to them ("the fourth proviso").

```xml
<subsection eId="sec_7__subsec_1">
  <num>(1)</num>
  <intro eId="sec_7__subsec_1__intro">
    <p>The transfer of teachers under sections 4, 5 and 6 shall ordinarily …:</p>
  </intro>
  <proviso eId="sec_7__subsec_1__proviso_1">
    <content eId="sec_7__subsec_1__proviso_1__content">
      <p>Provided that, the transfer may be made even after the month of April …:</p>
    </content>
  </proviso>
  <proviso eId="sec_7__subsec_1__proviso_2">…</proviso>
</subsection>
```

A proviso may itself contain clauses:

```xml
<proviso eId="sec_20__proviso_1">
  <intro eId="sec_20__proviso_1__intro">
    <p>Provided that, such repeal shall not affect,-</p>
  </intro>
  <clause eId="sec_20__proviso_1__cl_a">
    <num>(a)</num>
    <content eId="sec_20__proviso_1__cl_a__content">
      <p>anything done or any action taken under the said Act; or</p>
    </content>
  </clause>
</proviso>
```

## Explanations

Akoma Ntoso has no `explanation` element. Indian-style Explanations use the
generic hierarchical container:

```xml
<hcontainer eId="sec_5__hcontainer_1" name="explanation">
  <content eId="sec_5__hcontainer_1__content">
    <p>Explanation:- For the purpose of this section, population means …</p>
  </content>
</hcontainer>
```

## Definitions

In a section whose heading contains "Definition" or "Definitions", the defined
term is wrapped in `<def>` and linked to a `TLCTerm` declared in
`<meta><references>`:

```xml
<clause eId="sec_2__cl_k">
  <num>(k)</num>
  <content eId="sec_2__cl_k__content">
    <p eId="sec_2__cl_k__content__p_1">
      <def eId="sec_2__cl_k__content__p_1__def_1"
           refersTo="#unitOfSeniority">"Unit of seniority"</def>
       means for primary school teachers the Unit of Seniority is an
       Educational district …</p>
  </content>
</clause>
```

```xml
<references source="#nyayabandhu">
  <TLCTerm eId="unitOfSeniority"
           href="/akn/ontology/term/unitOfSeniority"
           showAs="Unit of seniority"/>
</references>
```

A term is recognised by the pattern `"Term" means|includes|shall mean`. The
`TLCTerm` identifier is the term slugified to lowerCamelCase.

## Schedules

Schedules are attachments, each holding a complete document with its own FRBR
identity:

```xml
<attachments>
  <attachment eId="att_1">
    <doc name="schedule">
      <meta>
        <identification source="#nyayabandhu">
          <FRBRWork>
            <FRBRthis value="/akn/in-ka/act/2020-03-26/4/!schedule_1"/>
            …
          </FRBRWork>
          …
        </identification>
      </meta>
      <mainBody eId="att_1__body">
        <hcontainer eId="att_1__hcontainer_1" name="schedule">
          <heading>SCHEDULE</heading>
          <subheading eId="att_1__hcontainer_1__subheading">(see section
            <ref href="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main#sec_2">2</ref>
            and
            <ref href="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main#sec_16">16</ref>)
          </subheading>
          <content eId="att_1__hcontainer_1__content">
            <table eId="att_1__hcontainer_1__table_1">…</table>
          </content>
        </hcontainer>
      </mainBody>
    </doc>
  </attachment>
</attachments>
```

A bare `#sec_2` inside a schedule would address the schedule itself, so
citations of the Act's sections from within a schedule are written as the
component URI plus fragment. See
[cross-references.md](cross-references.md#references-from-within-a-schedule).

## Tables

A table is a block element, so it appears inside `<content>` or `<intro>`,
never among a provision's child provisions. The first row is emitted as `<th>`,
subsequent rows as `<td>`.

```xml
<table eId="att_1__hcontainer_1__table_1">
  <tr eId="att_1__hcontainer_1__table_1__tr_1">
    <th eId="att_1__hcontainer_1__table_1__tr_1__th_1">
      <p eId="…__th_1__p_1">Sl. No.</p>
    </th>
    <th eId="att_1__hcontainer_1__table_1__tr_1__th_2">
      <p eId="…__th_2__p_1">Cadre of teachers</p>
    </th>
  </tr>
  <tr eId="att_1__hcontainer_1__table_1__tr_2">…</tr>
</table>
```

Tables split across a page break are joined; a row whose first cell is empty is
merged into the row above.

## Text in another language

Text in a language other than the requested one is preserved and tagged, not
deleted:

```xml
<p eId="preface__p_1">Ordered that the translation of
  <span eId="preface__p_1__span_1" xml:lang="kn-Latn-x-nudi"
    >PÀ£ÁðlPÀ gÁdå ¹«¯ï ¸ÉÃªÉUÀ¼ÀÄ …</span>
  in the English language, be published as authorised by the Governor of
  Karnataka …</p>
```

Under `--foreign mark` the run becomes `<omissis/>` instead:

```xml
<p eId="preface__p_1">Ordered that the translation of
  <omissis eId="preface__p_1__omissis_1"/> in the English language …</p>
```

The Act's title in the enacting language is additionally carried as a
Work-level `FRBRalias`. See [languages.md](languages.md).

## Ambiguous enumerators

`(i)`, `(v)` and `(x)` are valid in both an alphabetic and a roman sequence,
and both occur in this corpus:

| Provision | Reading |
| --- | --- |
| Teachers Transfer Act s.2(i) — follows `(h)` | alphabetic clause |
| Teachers Transfer Act s.10(1)(i) — opens a list | roman clause |

Resolution uses the nearest enumerators on either side:

1. An enumerator that follows its alphabetic predecessor (`h`→`i`, `u`→`v`,
   `w`→`x`) continues a letter list.
2. One that follows its roman predecessor (`iv`→`v`, `ix`→`x`) continues a
   roman list.
3. One that opens a list is settled by the next enumerator: `(ii)` after `(i)`
   means roman; `(j)` after `(i)` means alphabetic.
4. A lone enumerator with no neighbours is read as roman.

## Attribute values fixed by the schema

| Attribute | Permitted values |
| --- | --- |
| `eventRef/@type` | `generation`, `amendment`, `repeal` |
| `act/@contains` | `originalVersion`, `singleVersion`, `multipleVersions` |
| `keyword/@dictionary` | required; any string |

## Elements not currently emitted

`crossHeading` is supported by the tree builder but rare in this corpus.
`blockList`, `ul`/`ol`, `authorialNote`, `mod`/`quotedStructure` (used for
amendment text) and `temporalData` are not emitted.
