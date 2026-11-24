# Amendment consolidation: reasons and admin resolution guide

**Audit date:** 24 November 2026  
**Scope:** The 12 distinct amendment Acts in the current `data/acts` catalog. The isolated audit applied extracted instructions to each original principal Act and then tried each Act's amendments in publication order. It made no human corrections, fixture substitutions, approval decisions, or assumptions about commencement dates. Audit evidence is in branch `audit/automatic-consolidation-check`, `audit/report.json` (commit `156d5f1`).

Four amendments applied mechanically to their original principal Act: **Teachers 27/2021, Kannada Language 07/2024, Bangalore Palace 35/2025, and BBMP 12/2023**. This is a technical result, not legal approval. BBMP 12/2023 cannot yet be reached in the raw chronological chain because BBMP 29/2022 stops that chain. Every proposed consolidation still needs an administrator to verify the Gazette, legal effective date, predecessor version, and complete amendment coverage.

## How an administrator resolves an instruction

1. In **Admin → the Act timeline**, process the amendment and open **View changes**. Select the correct **approved predecessor**. Verify the instrument order and actual effective date against the Gazette and any commencement notification; record the evidence and confirm the date review. Publication date alone is not proof of commencement.
2. For a conflict, open **View amendment** at its recorded Gazette page, compare the quoted instruction with the predecessor, and choose **Edit proposal**. Correct the target, action, anchor, replacement wording, provision structure, or legal-effect classification as the source requires. Add a review note explaining the change. The source quotation itself is fixed.
3. Use **Inspect & bind exact matches**. Check the exact matched text, target, inline nodes, and incoming references. For protected inline text or references, use the linked **instruction desk** to make explicit slot or reference decisions. **Keep proposal changes**, then **Accept** only after the preview has no conflict and the wording matches the Gazette.
4. **Save review → Validate complete amendment batch**. Resolve *every* instruction, including separate commencement, repeal, savings, and multi-Act effects. Save a consolidated draft only when batch validation passes. Inspect the complete draft against the Gazette and approve that exact version in **Versions & visual editor**.

If the correct predecessor or source document is missing, obtain and import it before editing an instruction. Do not invent omitted statutory text, point a target at a merely similar provision, or accept a partial batch. A rejected instruction remains unresolved and blocks the batch. If an exact correction cannot be expressed safely in the admin interface, record the source and proposed change for an engineering fix, then rerun validation.

## Amendment-by-amendment findings

### Karnataka State Civil Services (Regulation of Transfer of Teachers) Act, 2020

| Amendment | Why the raw audit did or did not apply | Admin resolution |
| --- | --- | --- |
| **27/2021** | All 3 extracted instructions applied mechanically. Section 1 indicates retrospective effect from **29 April 2021**. | Verify that date and the Gazette wording; record the date evidence, inspect all 3 instructions, and approve the resulting version. |
| **06/2022** (Second Amendment Act, 2021) | `sec_2_op_1` quotes words to replace in the **long title**, but the original base contains **zero exact matches**. The raw sequence stops here. Its commencement date also needs a source-backed determination. | Compare the Gazette's long-title instruction with the approved predecessor and base transcription. Correct a transcription error in the base if the Gazette supports it; otherwise edit the proposal's exact old words and replacement to match the legally intended text. Inspect for one exact match, then review the other 22 extracted instructions and the commencement evidence. Do not weaken the expected match count to force a result. |
| **32/2022** | `sec_3_op_1` targets **section 7(1), sixth proviso**, which is absent from the original 2020 base. The chronological audit cannot reach it while 06/2022 conflicts. | Resolve and approve 06/2022 first; select that approved version as predecessor. Confirm the sixth proviso exists there and matches the Gazette. If still absent, locate the intervening Act or correct the source-backed base/provision structure before rebinding the target. |
| **27/2026** | `sec_2_op_1` targets **section 2, clause (ca)**, absent from the original base. The chronological audit is blocked earlier at 06/2022. | Complete the preceding Teachers amendments in order and select the latest applicable approved version. Verify clause (ca) is present and that all later instructions have the correct legal date. If it is absent, investigate the missing amendment or a source-backed parsing/numbering error. |

### Kannada Language Comprehensive Development Act, 2022

| Amendment | Why the raw audit did or did not apply | Admin resolution |
| --- | --- | --- |
| **07/2024** | All 4 instructions applied mechanically to the available principal Act. The audit did **not** establish the commencement date. | Compare all 4 changes with the Gazette, obtain the notification or statutory commencement evidence, set the actual date, validate the full batch, and approve the draft. |

### Bangalore Palace (Utilization and Regulation of Land) Act, 2025

| Amendment | Why the raw audit did or did not apply | Admin resolution |
| --- | --- | --- |
| **35/2025** | All 8 instructions applied mechanically after the extractor was corrected to recognize uppercase definition labels `(A)`–`(F)`. Its retrospective effect and commencement need legal review. | Check each definition and the rest of the amendment against the Gazette; record the statutory retrospective/date evidence and any distinct legal effects, then validate and approve. |

### Bruhat Bengaluru Mahanagara Palike Act, 2020 (BBMP)

**Chain dependency:** BBMP 29/2022 is the first raw chronological conflict. Consequently 12/2023, 17/2024, 37/2024, 07/2025, and 34/2025 have **not** been demonstrated to consolidate as one complete unreviewed chain, even where an individual amendment can apply to the original base.

| Amendment | Why the raw audit did or did not apply | Admin resolution |
| --- | --- | --- |
| **29/2022** | `sec_2_op_2` finds the relevant words, including a harmless spacing variant around `sub-section (2)`, but the replacement crosses an **inline reference boundary**. The engine refuses to flatten the linked reference silently. | Open the detailed instruction desk for this operation. Inspect the inline candidates, split the edit into exact text-slot changes, and explicitly decide whether the reference's displayed text and destination remain, change, or are removed, following the Gazette. Reinspect and validate the complete five-instruction batch. |
| **12/2023** | Its 3 instructions apply mechanically to the original base alone, but the raw sequence is blocked by 29/2022. | Approve 29/2022 first, choose that approved result as predecessor, and revalidate all 3 instructions against it. Resolve any new overlap before approval. |
| **17/2024** | `sec_4_op_2` omits provisions that have an **incoming reference** from section 142(4); the engine requires an explicit destination and displayed-text decision. Also, `sec_11_op_3` says to insert a proviso after **Explanation 3**, but the extractor left its insertion position unresolved. The raw sequence is blocked by 29/2022. | In the instruction desk, inspect section 142(4)'s reference and the Gazette's omission. Explicitly update or remove the reference as the law requires; do not leave a dead link. Review `sec_11_op_3` against the source and choose the exact insertion parent and position after Explanation 3. If the interface cannot represent that placement, request a source-backed engineering correction. Then validate all 33 instructions against the proper predecessor. |
| **37/2024** (BBMP and Certain Other Law Amendment Act, 2023) | `sec_2_op_1` targets **section 2, clause (26)**, but the current BBMP XML models numbered definitions as `subsection` nodes, so that path resolves to zero nodes. The Act also amends **Karnataka Act 14 of 1977**, whose principal text is absent from the catalog. The BBMP raw sequence is blocked by 29/2022. | Inspect the Gazette and BBMP base XML to determine whether the source-backed target is the definition represented as `sec_2__subsec_26`; correct the base structure or proposal selector only after that check. Obtain/import the 1977 principal Act and process its side of the amendment separately. Review the Act's validation/legal-effect instruction rather than inserting it as principal-Act wording. Validate both affected Acts. |
| **07/2025** (Second Amendment Act, 2024) | `sec_2_op_2` targets the **seventh proviso to section 144(15)(b)**, absent from the original base. The raw sequence is blocked by 29/2022. | Complete the earlier BBMP amendments, select the correct approved predecessor, and check whether that seventh proviso was introduced there. If not, locate the missing source or correct a proven provision-numbering error before targeting it. |
| **34/2025** | `sec_4_op_1` targets **section 240A(2)**, absent from the original base. The raw sequence is blocked by 29/2022. | Trace the Act that introduced section 240A and import/process it if missing; then select the resulting approved predecessor and inspect subsection (2). Do not create section 240A from this amendment unless the Gazette expressly directs that insertion. |

## Practical completion order

1. Clear **Teachers 06/2022** and **BBMP 29/2022** first; each blocks its later raw chain.
2. Import any missing predecessor text, especially **Karnataka Act 14 of 1977** for the second target of BBMP 37/2024, and any instrument that introduced BBMP section 240A or the seventh proviso to section 144(15)(b).
3. Process each Act's amendments in legally applicable order. Review effective dates separately from publication order, especially retrospective provisions and commencement by notification.
4. For every saved version, compare the consolidated provision text and all affected references with its Gazette evidence. Export the evidence package and keep the review notes with the approved version.

The audit reports only the **first observed conflict** for a failed batch. After fixing one, further conflicts may surface. A successful technical preview establishes XML and instruction consistency; the administrator's source comparison and date determination remain necessary before approval.
