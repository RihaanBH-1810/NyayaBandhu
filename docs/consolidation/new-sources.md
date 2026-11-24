# Teachers and Kannada Act source intake

## Unattended technical preparation

Technical preparation verifies the bundled base and all four distinct source
pairs by SHA-256, registers any missing amendments as pending proposals, and
leaves existing source records unchanged when run again. The candidate ZIP
contains four dated XML drafts, immutable source files, the pinned technical
decision profile, and a validation report. Build it from a shell with
`source .venv/bin/activate` and
`python -m akn_consolidator.teachers_candidates --output teachers-unapproved-candidates.zip`.
The preparation API remains available for technical intake, but the Act
overview uses the ordinary Upload amendment workflow.

The profile contains the earlier regression decisions for the 2021, second
2021, and 2026 instruments. The 2022 instrument uses extracted candidates.
The 2026 candidate is rebound to the predecessor that includes Act 32 of
2022. All four XML candidates pass the existing validator in isolation. These
files are **technical drafts**, not CMS approvals or legally determined
commencement dates. The normal amendment review and version approval gates
remain required before the public reader or approved export can use them.

Seven requested English instruments are available in the local source catalog. The three newly supplied downloads were separated where needed so each platform PDF represents one instrument. The unmodified downloaded files are retained under `sources/original-downloads/`.

| Instrument | Platform PDF | Generated XML | PDF pages | Parsed sections | CMS extraction |
| --- | --- | --- | ---: | ---: | --- |
| Teachers Act, 2020 (Act 04 of 2020) | `data/acts/2020/ka-0004-2020/karnataka-state-civil-services-regulation-of-transfer-of-teachers-act-2020__gazette__kan-eng.pdf` | `out/base_act/eng/tranfer_of_teachers.xml` | 19 | 20 | Base import succeeds |
| Teachers Amendment, 2021 (Act 27 of 2021) | `data/acts/2021/ka-0027-2021/transfer-of-teachers-amendment-act-2021__gazette__kan-eng.pdf` | `out/amendment/eng/First_ammendment.xml` | 4 | 3 | 3 candidates |
| Teachers Second Amendment, 2021 (Act 06 of 2022) | `data/acts/2022/ka-0006-2022/transfer-of-teachers-second-amendment-act-2021__gazette__kan-eng.pdf` | `out/amendment/eng/Second_ammendment.xml` | 8 | 13 | 23 candidates |
| Teachers Amendment, 2022 (Act 32 of 2022) | `data/acts/2022/ka-0032-2022/transfer-of-teachers-amendment-act-2022__gazette__eng.pdf` | `out/amendment/eng/Teachers_2022.xml` | 4 | 4 | 11 candidates; none blocked |
| Teachers Amendment, 2026 (Act 27 of 2026) | `data/acts/2026/ka-0027-2026/transfer-of-teachers-amendment-act-2026__gazette__kan-eng.pdf` | `out/amendment/eng/Third_ammendment.xml` | 8 | 7 | 11 candidates |
| Kannada Language Comprehensive Development Act, 2022 (Act 13 of 2023) | `data/acts/2023/ka-0013-2023/kannada-language-comprehensive-development-act-2022__excerpt__eng.pdf` | `out/base_act/eng/kannada_language_comprehensive_development_2022.xml` | 9 | 31 | Base import succeeds |
| Kannada Language Comprehensive Development Amendment, 2024 (Act 07 of 2024) | `data/acts/2024/ka-0007-2024/kannada-language-comprehensive-development-amendment-act-2024__gazette__kan-eng.pdf` | `out/amendment/eng/Kannada_2024.xml` | 4 | 3 | 4 candidates; none blocked |

The Teachers 2022 PDF consists of pages 19-22 of `sources/original-downloads/teachers-collection.pdf`. The Kannada base consists of pages 6-14 of `sources/original-downloads/kannada-base-prs-collection.pdf`; its later 2024 amendment appendix and PRS cover material were excluded. `sources/original-downloads/kannada-amendment-2024.pdf` is copied unchanged into the platform PDF directory.

The originals supplied by the user match these source locations: [Teachers Gazette collection](https://nlcbharat.org/wp-content/uploads/2024/04/7-The-Karnataka-State-Civil-Services-Regulation-of-transfer-of-teachers-Act-2020.pdf), [Kannada base PRS collection](https://prsindia.org/files/bills_acts/acts_states/karnataka/2023/Act13of2023Karnataka.pdf), and [Kannada amendment Gazette mirror](https://www.comply4hr.com/noti/2016/KASAR2024Feb26.pdf). The mirror files should be checked against official Gazette copies during legal review. SHA-256 hashes of the three received originals, in that order, are `146ba7df2280867bec369949bbde877b55ff2c2eed2ac77fcad22045e7cd5def`, `6979bd5e335d9e07b0d254783a3a8e7ea43cb1b1b64e209b2fd50e4695af0dd6`, and `a48589708b02658e7f2edc40b0148ee75628aefc15a592282cb42b81da9c662d`.

## What was checked

- All seven platform PDFs open, have the expected Act number, parse into English AKN, and pass the schema, identifier, reference, and language checks.
- Both bases import into the CMS. All five amendments register against the correct base and produce instruction manifests with PDF page evidence.
- The Kannada base loads in the reader as 31 sections. Its visual editor loads section 20(3). The 2024 amendment candidates apply to the original Kannada base in an isolated dry run; the resulting XML validates and contains both item (vii-a) and the replacement section 17(6).
- All eleven Teachers 2022 candidates apply cleanly to the reviewed post-Second demonstration expression, and the resulting XML validates. This is a technical dry run, not approval of the legal interpretation.
- An isolated CMS regression imports the Teachers base and all four amendments in chronological order, reviews each manifest using fixture decisions, previews and applies each batch, validates the final XML, and exports the approved test version. The old Third amendment fixture binds to the earlier post-Second predecessor; its target hashes and identities must be rebound to the post-2022 predecessor before the 2026 batch can be applied. The test performs that rebind explicitly.
- A separate isolated CMS regression previews, applies, validates, and exports the Kannada pair using a synthetic effective date. That date is only a test input and is not a determination of commencement.

## Review still required

The Teachers 2022 amendment directs substitution of the *fifth and sixth provisos* to section 7(1) with one proviso. The post-Second demonstration XML has an unusual proviso identifier order. The extractor proposes removal of the fifth and sixth provisions in document order, then insertion after the fourth. The reviewer must check that proposal against the Gazette and the displayed predecessor. All eleven candidates begin pending; the CMS cannot issue an approved consolidation until every instruction is accepted and the date is confirmed.

The Kannada 2024 amendment states that commencement is on a date appointed by notification. The Gazette Act alone does not establish that effective date. Record the notification and its date in the CMS before confirming or applying this amendment. The Teachers 2022 Act says it comes into force at once; a reviewer must still confirm the date basis in the manifest. Existing Teachers demonstration dates and decisions are fixture assumptions, not lawyer approval.

To review these instruments in the browser, run `source .venv/bin/activate` and `python webui/run.py`, then open `http://127.0.0.1:8000/admin`. Add each base Act, approve it after source comparison, and upload amendments in effective order. Choose the matching XML and PDF paths from the catalog. The `consolidation-data/seven-act-validation/` store contains technical intake checks and no lawyer approvals; it is separate from the normal workspace.
