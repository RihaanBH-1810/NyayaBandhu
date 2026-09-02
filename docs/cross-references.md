# Cross-references

How citations in the text become `<ref>` elements.

Implemented in `akn_parser/refs.py`.

## Guarantee

A `<ref>` is emitted only when its target exists in the document. Any citation
that cannot be resolved is left as plain text and reported. The output should
therefore never contain a dangling internal reference; the validator checks
this on every run and reports the count as `dangling`.

## What is recognised

Three kinds of citation, matched in this order:

| Kind | Examples |
| --- | --- |
| Provision chains | `section 7`, `sections 4, 5 and 6`, `sub-section (3)`, `clause (i) to (iv) of sub-section (1) of section 10` |
| The Schedule | `the Schedule`, `the First Schedule` |
| Ordinal provisos | `the fourth proviso` |

Keywords accepted for a provision chain: `section`, `sub-section`, `clause`,
`sub-clause`, `paragraph`, `sub-paragraph`, `rule`, `sub-rule`, `article`,
`item`, `chapter`, `part`, `category`. Both singular and plural, and both
hyphenated and unhyphenated spellings.

## Chains

A citation that names several levels is one citation, not several. It is parsed
outside-in and resolves to the innermost target:

```
clause (i) to (iv) of sub-section (1) of section 10
```

```
[("clause",     ["i", "iv"]),
 ("subsection", ["1"]),
 ("section",    ["10"])]
```

The outermost link (`section 10`) is resolved first, then each inner link is
resolved as a child of the last.

## Lists and ranges

When the innermost link names one provision, the whole citation text is wrapped
in a single `<ref>`:

```xml
specified under <ref href="#sec_7">section 7</ref>.
```

When it names several, each number is wrapped individually and the surrounding
words are left as text:

```xml
transfers made under sections <ref href="#sec_5">5</ref> and
<ref href="#sec_6">6</ref> under this Act
```

Ranges are treated as their endpoints; intermediate provisions are not
enumerated:

```xml
as defined in clause <ref href="#sec_10__subsec_1__cl_i">(i)</ref> to
<ref href="#sec_10__subsec_1__cl_iv">(iv)</ref> of sub-section (1) of section 10.
```

## Internal versus external

A citation is external — a reference to some other instrument — when another
instrument is named adjacent to it. External citations are left as plain text
and counted separately in the report.

**Named after the citation:**

```
the provisions of section 6 of the Karnataka General Clauses Act, 1899
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

The test is `of [the] <anything> Act|Code|Rules|Regulations|Ordinance|Constitution|Order|Notification`.

**Named before the citation:**

```
In the Karnataka … Act, 2020 (Karnataka Act 04 of 2020), in section 10, …
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

This is the form amending Acts use. The instrument must sit immediately before
the citation, so that a statute mentioned earlier in a long sentence cannot
capture an Act's references to itself.

**Excluded from the external test:** `of this Act`, `of the said Act`, `of the
present Act`. These are self-references and resolve internally.

No list of statute names is maintained; the test is structural.

## Relative citations

A citation that names no section is resolved against the provision the text
appears in. The search widens outwards:

1. The context element itself
2. Each ancestor of the context, innermost first
3. The top level of the document
4. Any descendant of the enclosing section

Step 4 is what allows section 10(2)'s `clauses (i) to (iv)` to resolve to the
clauses of section 10(1):

```xml
<subsection eId="sec_10__subsec_2">
  <content eId="sec_10__subsec_2__content">
    <p>The categories falling under clauses
      <ref href="#sec_10__subsec_1__cl_i">(i)</ref> to
      <ref href="#sec_10__subsec_1__cl_iv">(iv)</ref> are eligible …</p>
  </content>
</subsection>
```

The outermost link of a chain may itself be relative. In `clause (b) of
sub-section (2)`, no section is named, so the subsection is resolved against
the context before the clause is looked up beneath it.

## Sections inside chapters

In an Act with chapters a section is not at the top of the tree — section 208
of the BBMP Act has the eId `chp_XV__sec_208`. A citation of `section 208`
matches on the last component of the identifier, provided that match is
unambiguous.

## Keyword aliases

Indian drafting is not consistent about the name of a level. The Teachers
Transfer Act calls the same roman list `sub-clause (i)` in s.5(ii) and
`clauses (i) to (iv)` in s.10(2). Both spellings therefore accept both element
types:

| Keyword | Element types tried, in order |
| --- | --- |
| `section` | `sec` |
| `sub-section` | `subsec` |
| `clause` | `cl`, `subcl`, `point` |
| `sub-clause` | `subcl`, `cl` |
| `paragraph` | `para`, `subpara` |
| `item` | `item`, `cl` |
| `category` | `cl`, `subcl` |

## Provisos

Provisos have no `<num>`, so they are counted within their parent. An ordinal
reference resolves against the enclosing provision:

```xml
the limit prescribed in
<ref href="#sec_7__subsec_1__proviso_4">the fourth proviso</ref>, shall not …
```

Ordinals `first` through `tenth` are recognised.

## The Schedule

`the Schedule` resolves to the first attachment:

```xml
such other posts … as specified in <ref href="#att_1">the Schedule</ref>;
```

## References from within a schedule

A schedule is a separate component of the document. A bare `#sec_2` inside it
would address the schedule, so a citation of the Act's sections from within a
schedule is written as the expression component URI plus fragment:

```xml
<subheading eId="att_1__hcontainer_1__subheading">(see section
  <ref href="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main#sec_2">2</ref> and
  <ref href="/akn/in-ka/act/2020-03-26/4/eng@2020-03-27/!main#sec_16">16</ref>)
</subheading>
```

## Unresolved citations

A citation that is neither external nor resolvable is left as plain text and
listed in the report with the provision it appears in:

```
    unresolved     : 9 citation(s)
        (top level): 'article 243' -- no matching provision in this Act
        chp_IV__sec_19__subsec_1__proviso_2__cl_k__subcl_ii: 'section 171e'
            -- no matching provision in this Act
```

Reasons reported:

| Reason | Meaning |
| --- | --- |
| `no matching provision in this Act` | Nothing with that number exists at any candidate level |
| `no <keyword> <n> in this Act` | The outermost link of a chain could not be anchored |
| `<keyword> <n> not found under <eId>` | An inner link of a chain had no such child |
| `no such proviso` | An ordinal proviso reference exceeded the provisos present |

Each distinct citation is reported once per provision, even though it is
examined at several depths.

## Known gaps

- Citations of the Constitution (`Article 243`) and of central Acts by a
  phrasing the external test does not match are reported as unresolved. They
  are correctly left unlinked, but they are not identified as external.
- An amending Act's citations point into the base Act. They are left unlinked
  and reported. Turning them into references carrying the base Act's FRBR URI
  requires loading the base Act alongside the amendment, which is part of
  consolidation and is not implemented.
- External citations are left as plain text rather than being marked up with
  the cited instrument's FRBR URI.
