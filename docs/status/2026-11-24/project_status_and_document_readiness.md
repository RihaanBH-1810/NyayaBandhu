# Document readiness and project branches

Status checked: 24 November 2026. Repository: `NyayaBandhu`. Current branch: `feat/automatic-corpus-amendments`.

## Current result

The catalog contains **21 PDFs representing 18 distinct Acts**. The current intake check was rerun against every catalog PDF. Parsing/intake and automatic consolidation are separate results: a PDF can import successfully while its amendment instructions still fail to apply.

The last complete automatic-consolidation audit covered the earlier 20-PDF corpus: **5 of 12 amendments pass mechanically in their publication-order chains**. It predates the newly added Municipal Corporations compilation. That compilation supplies the correct principal Act, but its conversion fails, so its side of Act 37/2024 has not been demonstrated to consolidate. Publication-order checks do not establish the correct legal effective-date order.

## Every PDF: conversion and intake

| Act identity | PDF / edition | Current result |
| --- | --- | --- |
| ka-0004-2020 | Karnataka State Civil Services Regulation Of Transfer Of Teachers Act 2020 — gazette, kan-eng | base imported |
| ka-0027-2021 | Transfer Of Teachers Amendment Act 2021 — gazette, kan-eng | amendment imported and extracted |
| ka-0006-2022 | Transfer Of Teachers Second Amendment Act 2021 — gazette, kan-eng | amendment imported and extracted |
| ka-0032-2022 | Transfer Of Teachers Amendment Act 2022 — gazette, eng | amendment imported and extracted |
| ka-0027-2026 | Transfer Of Teachers Amendment Act 2026 — gazette, kan-eng | amendment imported and extracted |
| ka-0013-2023 | Kannada Language Comprehensive Development Act 2022 — excerpt, eng | base imported |
| ka-0007-2024 | Kannada Language Comprehensive Development Amendment Act 2024 — gazette, kan-eng | amendment imported and extracted |
| ka-0053-2020 | Bruhat Bengaluru Mahanagara Palike Act 2020 — gazette, eng | base imported |
| ka-0053-2020 | Bruhat Bengaluru Mahanagara Palike Act 2020 — gazette, kan | alternate edition available |
| ka-0016-2026 | Chandraguthi Renukamba Kshetra Act 2026 — gazette, kan-eng | base imported |
| ka-0013-2023 | Kannada Language Comprehensive Development Act 2022 — gazette, eng | alternate edition available |
| ka-0007-2024 | Kannada Language Comprehensive Development Amendment Act 2024 — gazette, kan | alternate edition available |
| ka-0014-2025 | Bangalore Palace Utilization And Regulation Of Land Act 2025 — gazette, eng | base imported |
| ka-0035-2025 | Bangalore Palace Utilization And Regulation Of Land Amendment Act 2025 — gazette, eng | amendment imported and extracted |
| ka-0029-2022 | Bruhat Bengaluru Mahanagara Palike Amendment Act 2022 — gazette, kan | amendment imported and extracted |
| ka-0012-2023 | Bruhat Bengaluru Mahanagara Palike Amendment Act 2023 — gazette, kan | amendment imported and extracted |
| ka-0017-2024 | Bruhat Bengaluru Mahanagara Palike Amendment Act 2024 — gazette, kan | amendment imported and extracted |
| ka-0037-2024 | Bruhat Bengaluru Mahanagara Palike And Certain Other Law Amendment Act 2023 — gazette, eng | amendment imported and extracted |
| ka-0007-2025 | Bruhat Bengaluru Mahanagara Palike Second Amendment Act 2024 — gazette, kan | amendment imported and extracted |
| ka-0034-2025 | Bruhat Bengaluru Mahanagara Palike Amendment Act 2025 — gazette, kan | amendment imported and extracted |
| ka-0014-1977 | Karnataka Municipal Corporations Act 1976 — consolidated-through-act-0001-2022, eng | DuplicateEId: eId 'chp_IX' generated twice (for <chapter> and <chapter>). This means the parsed hierarchy is wrong, not that the identifier needs a suffix. |

“Base imported” means conversion and temporary CMS import succeeded. “Amendment imported and extracted” means instructions were produced, not that they were successfully applied or approved. Alternate editions are retained as sources; they do not count as additional amendments. The intake run uses a temporary store and does not populate or approve a live admin workspace.

## Amendment application

| Amendment | Automatic result | Remaining reason / scope |
| --- | --- | --- |
| ka-0027-2021 | Pass | Teachers: all 3 instructions apply. |
| ka-0006-2022 | Conflict | Teachers: now passes long-title and global wording steps; stops at sec_4_op_3 because the match affects protected inline text. |
| ka-0032-2022 | Blocked by earlier amendment | Teachers: original base lacks section 7(1), sixth proviso. Full chain is blocked by 06/2022; not yet verified against a completed predecessor. |
| ka-0027-2026 | Blocked by earlier amendment | Teachers: original base lacks section 2 clause (ca). Full chain is blocked by 06/2022. |
| ka-0007-2024 | Pass | Kannada Language: all 4 instructions apply. Commencement evidence still requires verification. |
| ka-0035-2025 | Pass | Bangalore Palace: all 8 instructions apply. Retrospective/date evidence still requires verification. |
| ka-0029-2022 | Pass | BBMP: exact substitutions across complete references now apply; all 5 instructions pass. |
| ka-0012-2023 | Pass | BBMP: all 3 instructions pass, including after 29/2022. |
| ka-0017-2024 | Conflict | BBMP: omission has an incoming reference from section 142(4); explicit reconciliation is still required. Also has an unresolved insertion after Explanation 3. |
| ka-0037-2024 | Blocked by earlier amendment | BBMP: clause (26) selector differs from the base XML definition structure. The other principal Act is now cataloged as ka-0014-1977, but cannot yet convert. BBMP chain blocked by 17/2024. |
| ka-0007-2025 | Blocked by earlier amendment | BBMP: original base lacks the seventh proviso to section 144(15)(b). Chain blocked by 17/2024. |
| ka-0034-2025 | Blocked by earlier amendment | BBMP: original base lacks section 240A(2). Newly supplied compilation appends Act 1/2022 introducing section 240A, but that instrument has not been separately extracted/applied. Chain blocked by 17/2024. |

A failed batch reports its first encountered conflict; resolving it can expose further issues. A mechanical pass is not evidence of an approved legal consolidated version. The previously tested reviewed Teachers fixtures are a different workflow and do not demonstrate that raw extraction succeeds without intervention.

## Branch map

| Branch | Tip | Stage / purpose |
| --- | --- | --- |
| `main` | `4042c8c` | Committed integrated baseline: parser, review/consolidation CMS, visual workspace, Windows packaging, additional Karnataka sources, and recoverable deletion. Also matches local origin/main; remote was not fetched. |
| `feat/amendment-provenance-ux` | `d37af4c` | Principal-Act identity checks and source provenance review. |
| `feat/section-level-review` | `00fd83a` | Section-grouped amendment review and visual editing, plus UI fixes. |
| `feat/teachers-candidate-chain` | `2cc8052` | Four Teachers amendment candidate preparation, source-backed prior effects, and blockers scoped to the version date. |
| `feat/automatic-corpus-amendments` | `2cc8052` | Current checkout. New automation rules, catalog migration/admin intake work, 21-PDF corpus, and new principal Act are in the UNCOMMITTED working tree. Its committed tip is identical to the Teachers branch. |
| `audit/automatic-consolidation-check` | `156d5f1` | Isolated feasibility audit script and historical report. No audit worktree is currently open. Its report predates the newest working-tree improvements and 1977 compilation. |
| `feature/amendment-consolidation` | `24b9a04` | Earlier reviewed consolidation engine and browser CMS implementation. |
| `feature/visual-consolidation-workspace` | `9db8594` | Earlier integrated visual review/consolidation workspace. |
| `feature/windows-installer` | `26cf5fd` | Earlier Windows installer stage; later installer fixes also exist in main. |
| `research/karnataka-corpus-evaluation` | `9156c3c` | Karnataka source evaluation and source-intake research snapshot. This is separate from the uploaded data corpus audit. |
| `demo/bluebell-editor` | `44cd4a0` | Earlier Bluebell editing prototype and PDF comparison. |
| `demo/visual-editor` | `e69ad48` | Earlier direct visual editing prototype and provision layout. |
| `fix/parser-cli-issues-3-9` | `50b96a5` | Parser packaging and CLI fixes. |
| `cli-v2` | `8e0aa7a` | Earlier CLI output and web viewer stage. |
| `v2-improvements` | `9dff4e1` | Earlier provision rendering and parser output improvements. |
| `webview` | `1c4332c` | Earlier web viewer layout stage. |
| `installationscripts` | `3e7181d` | Earlier portable Python and Windows install/start scripts. |

Branch names mark development snapshots, not independently verified releases. Capabilities may already be incorporated into later branches. The current corpus readiness verdict applies to the present working tree, not every historical branch.

## Reproducibility and remaining work

**The latest work is not yet saved as commits.** Creating the automation branch did not commit the pre-existing migration, UI, parser, or engine changes. Checking out a clean copy of its current tip will not reproduce the 21-PDF corpus or recent automation results. The brief reports are outside the NyayaBandhu Git repository.

The previous automation change passed 34 targeted tests. The new annotated compilation remains a known conversion failure; it prevents claiming that all current PDFs work. This report uses a fresh full intake check and the latest saved 20-PDF automatic-consolidation audit. It does not claim a new full test-suite pass.

Next work: support the annotated Municipal Corporations compilation, extract the appended Act 1/2022 with page provenance, reconcile protected text and incoming references, resolve exact insertion/definition structures, complete both chains, then rerun the full corpus audit and save the implementation as reviewable commits.

Evidence: `brief/current_corpus_intake_report.json`, `brief/automatic_amendment_branch_audit.json`, `brief/municipal_corporations_source_intake.md`, and the local Git branch/status output.
