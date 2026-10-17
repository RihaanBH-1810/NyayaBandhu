# Teachers Act corpus and explicit decisions

## Inputs and coverage

The base is `out/base_act/eng/tranfer_of_teachers.xml` with `data/v0s/kan_eng/tranfer_of_teachers.pdf`. The three amendment XMLs are under `out/amendment/eng/`, with corresponding PDFs under `data/ammendments/`; their filenames retain the repository's `ammendment` spelling.

| Instrument | Work URI suffix | Covered outer sections | Operations | Demo effective date |
| --- | --- | ---: | ---: | --- |
| Base | `2020-03-26/4` | — | — | 2020-03-27, as published |
| First | `2021-10-01/27` | 3 | 3 | 2021-04-29 |
| Second | `2022-01-17/6` | 13 | 23 | 2022-01-18 |
| Third | `2026-04-09/27` | 7 | 11 | 2026-04-10 |

Every extracted operation has PDF page evidence and an unchanged source quotation. The full reviewed manifests and expected XML snapshots are checked in under `tests/fixtures/consolidation/`. The snapshots freeze the engine's demonstrated output and are regression oracles, **not independently lawyer-certified gold standards**.

## Decisions requiring legal review

1. **Commencement.** First section 1 supplies the retrospective 29 April 2021 date. Second and Third say “at once”; the fixtures explicitly assume their publication dates. Extraction leaves those dates unresolved. A real reviewer must determine commencement and record the basis; the script labels its dates as fixture assumptions.
2. **Second, long title.** The amendment quotes “Government Primary Schools and Government High Schools”. The base contains `Government Primary school sand Government High schools`. The base PDF's extracted text also contains `school sand`; the fixture does not assert that this is merely a parser error. It records an explicit target-range decision while retaining the amendment quotation unchanged.
3. **Second, preamble.** The base has `High schools` with different capitalization. The fixture explicitly chooses that target spelling; the engine performs no fuzzy or case-insensitive substitution.
4. **Second, global School substitution.** The fixture lists five exact, case-sensitive whole-word occurrences. It does not automatically expand to lowercase `school` or plural `Schools`. Whether the instruction requires a wider interpretation remains a legal review question. The five occurrences and their original offsets are frozen in the manifest.
5. **Second, section 2(i).** `Schedule` occurs inside an existing reference. The fixture explicitly permits changing its displayed text to `Schedule-I` while retaining the reference to the first schedule.
6. **Second, section 2(k).** The source instruction uses `Revenue Division`, while the base has `Revenue division`. The fixture records the explicit target spelling for the insertion.
7. **Third, section 10.** Omission of clause (vii) and omission of `and (vii)` in subsection (4) are linked by an explicit same-batch reference-removal decision. The reference to clause (vi) and all unrelated XML survive.
8. **Third, Schedule-I.** The final group anchor is printed `II)` in the base. Printed-number normalization identifies it as `II`; the original label is not rewritten.
9. **Other legal effects.** Commencement and repeal/savings clauses are classified separately rather than appended to the principal Act's text. Their source quotations remain in the manifest. The engine does not decide their effect on other instruments or pending proceedings.

## Demonstrated results

- First inserts subsection 10(6).
- Second expands the scope wording, adds lecturer/college definitions and transfer provisions, names Schedule-I, and adds Schedule-II.
- Third preserves the lecturer definition's stable identity when renumbering (ca) to (cb), inserts a new Critical Posts definition at (ca), changes transfer provisions, replaces section 6, adds the maternity-related clause, removes clause 10(1)(vii) and its affected inline reference, and extends Schedule-I.
- All three assembled expressions validate. The final expression has 32 passive textual-modification records and 37 applied operation keys. Existing language spans and tested untouched sections remain unchanged.

## Current limits

- Deterministic extraction covers this English corpus's instruction patterns. Scanned PDFs need OCR outside this module. Other drafting styles may need reviewed manual manifest edits or new rules. Extraction and XSD validation do not prove semantic completeness.
- Source tables are recovered from generated amendment XML and require PDF comparison. New fragment text does not automatically acquire definition or citation annotations. Existing protected inline markup survives edits; newly introduced citations remain plain text for later reviewed annotation.
- Direct incoming-reference decisions cover `<ref href>` links. Other semantic relationship types are not automatically reconciled. The existing validator also treats URI fragments conservatively, including external fragments, and may block a legitimate external reference for review.
- Schedule insertion supports the demonstrated existing-metadata template and final roman-group insertion, not arbitrary table merges or column changes.
- The base timeline begins at its as-published date. An amendment predating that snapshot requires an earlier registered/constructed predecessor; this phase does not reconstruct missing earlier law.
- No notification discovery, territorial applicability inference, Kannada conversion, government attestation, accounts, or publication. The browser CMS, API, and local storage are intended for trusted local use.
- No automatic cascade rebuild: corrections explicitly stale downstream versions and require preview/application/approval again. This makes the rebuild reviewable.
- Raw XML inspection can read unapproved versions. Only the ZIP export route asserts the version has a current approval; its provenance still limits coverage to registered sources.
