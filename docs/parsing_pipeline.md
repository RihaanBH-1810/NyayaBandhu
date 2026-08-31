# BBMP Act to Akoma Ntoso XML Mapping Reference

This document outlines how the structural and semantic elements of the BBMP Act are mapped to the Akoma Ntoso (LegalDocML) XML standard by the `XML-gen.py` script.

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 2em;">

## 1. Overall Document Structure & Metadata
The entire document is wrapped in the `<akomaNtoso>` root element and an `<act>` element. 
It begins with a `<meta>` block containing strict FRBR (Functional Requirements for Bibliographic Records) identifiers, lifecycle events, and classifications, followed by the `<preface>` and the main `<body>`.

```xml
<?xml version="1.0" ?>
<akomaNtoso xmlns="[http://docs.oasis-open.org/legaldocml/ns/akn/3.0](http://docs.oasis-open.org/legaldocml/ns/akn/3.0)">
  <act name="TheBruhatBengaluruMahanagaraPalikeAct2020">
    <meta>
      <!-- FRBR Identifiers, Publication details, Lifecycle, Classification -->
    </meta>
    <preface>
      <!-- Preliminary gazette text, notification numbers, preamble -->
    </preface>
    <body>
      <!-- Chapters and Sections -->
    </body>
    <components>
      <!-- Schedules -->
    </components>
  </act>
</akomaNtoso>
```
</div>

## 2. Hierarchical Elements (The Body)
The Indian legislative drafting style uses a strict hierarchy. The script maps this to nested Akoma Ntoso elements. Each level receives a unique `eId` (Expression ID) and `wId` (Work ID) for precise referencing.

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 1.5em;">

### A. Chapter
Chapters are the highest grouping within the body. They contain a number (`<num>`) and an extracted `<heading>`.

```xml
<chapter eId="chp_I" wId="chp_I">
  <num>I</num>
  <heading>PRELIMINARY</heading>
  <!-- Sections go here -->
</chapter>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 1.5em;">

### B. Section
Sections are the primary functional unit. They contain the section number and the section title.

```xml
<section eId="sec_1" wId="sec_1">
  <num>1.</num>
  <heading>Short title and commencement</heading>
  <content>
    <p>(1) This Act may be called the Bruhat Bengaluru Mahanagara Palike Act, 2020.</p>
  </content>
  <!-- Subsections go here -->
</section>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 1.5em;">

### C. Subsection
Denoted by numbers in parentheses, e.g., "(1)", "(2)". Nested inside `<section>`.

```xml
<subsection eId="sec_1-subsec_2" wId="sec_1-subsec_2">
  <num>(2)</num>
  <content>
    <p>The provisions of the Act shall come into force on such date...</p>
  </content>
</subsection>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 1.5em;">

### D. Clause
Denoted by lowercase letters in parentheses, e.g., "(a)", "(b)". Nested inside `<subsection>` (or directly in `<section>`).

```xml
<clause eId="sec_2-subsec_7-clause_a" wId="sec_2-subsec_7-clause_a">
  <num>(a)</num>
  <content>
    <p>a house, out-house, stable, privy, shed...</p>
  </content>
</clause>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 2em;">

### E. Subclause
Denoted by lowercase Roman numerals in parentheses, e.g., "(i)", "(ii)". Nested inside `<clause>`.

```xml
<subclause eId="sec_4-subsec_4-clause_i-subclause_ii" wId="sec_4-subsec_4-clause_i-subclause_ii">
  <num>(ii)</num>
  <content>
    <p>Government shall, after consulting the corporation, determine...</p>
  </content>
</subclause>
```
</div>

## 3. Semantic Tags & Special Blocks

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 1.5em;">

### A. Definitions (`<def>`)
In Section 2 (the definitions section), the specific terms being defined are wrapped in semantic `<def>` tags to allow for automated glossary extraction.

```xml
<subsection eId="sec_2-subsec_1" wId="sec_2-subsec_1">
  <num>(1)</num>
  <content>
    <p>
      <def>Annual Financial Statement</def>
       means the statement published by the Corporation...
    </p>
  </content>
</subsection>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 1.5em;">

### B. Cross-References (`<ref>`)
Whenever the text explicitly mentions another section (e.g., "section 208"), it is hyperlinked to the corresponding `eId` within the document.

```xml
<p>
  Corporation under 
  <ref href="#sec_208">section 208</ref>
  ;
</p>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 1.5em;">

### C. Provisos
Indian laws frequently use "Provided that...". These are mapped to a generic `<block>` element with the attribute `name="proviso"`.

```xml
<block name="proviso">
  <content>
    <p>Provided that the number of seats so reserved for the Backward Classes...</p>
  </content>
</block>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid; margin-bottom: 2em;">

### D. Explanations
Similar to provisos, explicit "Explanation:" blocks are wrapped with `name="explanation"`.

```xml
<block name="explanation">
  <content>
    <p>Explanation:- For the purpose of this section population means...</p>
  </content>
</block>
```
</div>

<div style="page-break-inside: avoid; break-inside: avoid;">

## 4. End-Matter (Schedules)
Schedules are appended at the end of the Act. They are treated as separate documents within a `<components>` collection and mapped using the `<schedule>` tag.

```xml
<components>
  <component>
    <schedule eId="sch_first" wId="sch_first">
      <num>FIRST SCHEDULE</num>
      <content>
        <p>(See section   107  )</p>
        <p>(A) Core Functions.-</p>
        <p>i. Urban planning including town planning,</p>
      </content>
    </schedule>
  </component>
</components>
```
</div>