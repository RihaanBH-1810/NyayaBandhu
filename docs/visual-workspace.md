# Visual consolidation workspace

Branch: `feature/visual-consolidation-workspace`

This branch combines visual base-text review, amendment consolidation, version
approval and a reader portal. It uses the existing consolidation engine and store.
The Bluebell, standalone visual-editor and original consolidation branches remain
available. Nothing in this workflow overwrites `out/` or the source PDFs.

## Start here

Run from the repository directory. Stop another server on port 8000 before starting.

```bash
git switch feature/visual-consolidation-workspace
source .venv/bin/activate
export PYTHONPATH="$PWD/scripts"
export NYAYA_CONSOLIDATION_DIR="$PWD/consolidation-data/teachers-demo"
python webui/run.py
```

| URL | Purpose |
| --- | --- |
| `http://127.0.0.1:8000/admin` | Acts dashboard, review and version approval |
| `http://127.0.0.1:8000/library` | Reader landing page |
| `http://127.0.0.1:8000/library/search` | Search approved Acts |
| `http://127.0.0.1:8000/viewer` | Previous generated-XML viewer and standalone visual review |
| `http://127.0.0.1:8000/consolidation` | Previous detailed consolidation desk |
| `http://127.0.0.1:8000/docs` | Interactive API documentation |

The root URL now opens the reader landing page. The previous root viewer moved to
`/viewer`; its conversion, document, raw-XML and review endpoints remain available.
The admin header's **More** menu contains links to the previous viewer and
consolidation desk.
This branch does not need npm, a JavaScript build or Bluebell installed.

To create a **new populated demonstration**, use a fresh store before starting:

```bash
export NYAYA_CONSOLIDATION_DIR="$PWD/consolidation-data/visual-demo-$(date +%Y%m%d-%H%M%S)"
python scripts/consolidation_demo.py --store "$NYAYA_CONSOLIDATION_DIR"
python webui/run.py
```

That script imports the Teachers Act, replays the three reviewed amendment
fixtures and approves four versions using a fixture-reviewer name. It is useful
for exploring the timeline and historical reader. Its choices are demonstration
fixtures, not a lawyer's attestation. Existing populated stores are never reset.

For a **hands-on review from the beginning**, start with an empty store instead:

```bash
export NYAYA_CONSOLIDATION_DIR="$PWD/consolidation-data/visual-manual-$(date +%Y%m%d-%H%M%S)"
python webui/run.py
```

## Lawyer walkthrough: base Act to approved amendment

1. Open `/admin` and choose **Add Act**. Enter your reviewer name and import reason.
   Select `base_act/eng/tranfer_of_teachers.xml` and the matching
   `v0s/kan_eng/tranfer_of_teachers.pdf`. The PDF selector matches filenames when
   possible; check both selections before importing. The upload section also
   accepts a PDF and optional generated XML. Without XML it runs the existing
   English parser; this requires extractable PDF text.
2. Open **Versions & visual editor**. Choose **Visual edit** on the base draft.
   Search/select a provision on the left. Click the wording or heading in the
   **Draft provision** pane to edit it directly. The original remains beside it.
   Numbered subsections and clauses keep their numbers beside their text.
3. Open **Source gazette** and compare the wording. Shaded inline references,
   definitions and language spans stay protected. Text around those elements is
   editable. Schedule and table-cell wording is editable with table structure
   fixed. Base provisions also have add, remove, renumber and move controls.
   Those controls perform one structural action per revision. Save wording edits
   before choosing a structural action. Newly added provisions need their
   placeholder wording replaced in a subsequent draft before approval.
4. Enter reviewer name/reason plus the source, actual PDF page numbers and a
   source quotation supporting the correction. **Preview revision** validates
   the assembled XML and shows its result and difference. **Save draft revision**
   creates an immutable version and returns to the version list. Reopen that
   draft to continue editing. No wording change is needed just to approve a base
   that already matches the gazette.
5. Choose **Inspect & approve**, read the exact version, then **Approve exact
   version**. Approval records the reviewer and exact XML hash. The base becomes
   available in the reader and as an amendment predecessor.
6. Choose **Upload amendment** and select `amendment/eng/First_ammendment.xml`
   with `ammendments/First_ammendment.pdf`. On the timeline, **Process amendment**
   extracts reviewable instructions. Open **View changes** afterwards.
7. Confirm the principal Act identity, effective date and instrument order.
   Record the actual commencement evidence and check the date confirmation.
   The First fixture uses `2021-04-29`, from section 1's retrospective wording;
   verify it against Gazette PDF page 3 for your own review.
8. The shared two-column canvas shows the predecessor and proposed provision
   together. Insertions are green, substitutions yellow and omissions red.
   Changed paragraphs are highlighted without stripping inline links. Expand
   **Exact wording difference** for a word comparison. Use the change filter,
   previous/next buttons or provision dropdown to navigate.
9. **View amendment** opens the source drawer at the recorded Gazette page.
   For the First amendment, compare section 2 on PDF pages 3–4: it inserts
   subsection (6) after section 10(5). Use **Edit proposal** to correct the target,
   action, wording, child provisions or table rows as necessary. **Inspect & bind
   exact matches** checks the selected target and records its preconditions;
   then **Keep proposal changes** returns it to pending review. Complex inline
   or reference reconciliation remains available through the linked detailed
   instruction desk.
10. **Accept** each checked instruction. Commencement and repeal/savings are
    separately classified legal effects; they do not become extra principal-Act
    paragraphs. **Reject** requires a note and leaves that instruction unresolved.
    Rejection blocks the batch until corrected; it never drops an amendment.
11. **Save review** records a new instruction revision. **Validate complete
    batch** previews every reviewed instrument for that effective date against
    the selected predecessor. Resolve any wording, reference, date, coverage or
    XML conflict. **Save consolidated draft** persists a successful preview.
12. In **Versions & visual editor**, inspect and approve the consolidated draft.
    Open the reader and compare the base and amended versions: subsection 10(6)
    should appear only in the amended version. Download its XML/PDF or the
    evidence ZIP from the admin version list.

Repeat for later amendments in effective-date order. The Second and Third
fixtures include more complex wording and reference decisions: consult
[fixture decisions](consolidation/fixture-decisions.md) and the original desk
where advanced decisions are needed. The populated demo already includes these
approvals; use the empty-store workflow to practice applying them yourself.

## Subsequent corrections and version control

- Every source PDF/XML pair is an immutable snapshot in the local store. Drafts
  and approved expressions have their own content hashes; source files remain
  untouched. All work-changing actions require a reviewer/reason and a current
  work revision. Manifest saves also require the manifest revision.
- Saving an edited draft replaces it with another draft and makes the previous
  draft stale. Old XML remains inspectable. An outdated browser tab receives a
  conflict instead of overwriting the newer work.
- Editing an approved base or consolidated expression creates a draft correction.
  The approved text remains current until the correction is approved. Approval
  supersedes that version and makes dependent consolidated versions stale, so
  they must be rebuilt. Repeated edits of the correction draft still supersede
  the original approved predecessor.
- Structural corrections to base XML use the visual editor. Statutory structural
  amendments use the amendment workbench and retain their instruction evidence.
  A consolidated draft must be approved before starting an editorial wording
  correction. The editor preserves stable identities for surviving elements;
  removed identities become tombstones and new elements receive new identities.
- Revision conflict, XML hash and preview-hash checks apply on the server. A
  changed review invalidates its dependent versions. Approval rechecks schema,
  identifiers, references and language constraints and, for consolidation,
  replays the instruction coverage against the predecessor.
- These are legislative data versions in SQLite and content-addressed files.
  They are separate from Git branches, which version the application code.

## Reader and related documents

The blue reader portal searches real registered Acts with approved, non-stale
versions effective on or before today. Its version selector retrieves each
version's actual XML rendition. Historical approved versions remain readable;
superseded or invalidated revisions remain in the admin history. The coverage
notice reports unresolved registered amendments for the chosen date. It does not
assert that every external gazette has been registered.

The XML modal displays actual stored XML. PDF download renders the selected
reviewed text; source Gazette PDFs remain separate evidence. **Report issue**
stores a message against the exact version and displays it in the admin
**Reader issues** tab. There is no email delivery or issue resolution workflow.

The admin rules/regulations panel can link a reviewed PDF from `data/`, with its
title, category, kind and date. It snapshots the PDF and audits the relationship.
The reader exposes those linked documents beside the approved Act. This is a
document relationship, not automatic subordinate-legislation consolidation.

## Design decisions and implementation

The screen design follows `../brief/nyayabandhu_ui_plan_agent_spec.md` and the
accompanying video: monochrome admin rail, searchable dashboard, timeline/rules
split, shared comparison canvas, Gazette drawer, and blue public reader.

The specification's suggested React stack was adapted to the repository's
FastAPI/Jinja and native JavaScript stack. This keeps one server and uses the
existing review/consolidation engine, with no second database or frontend build.
The native dialog, shared grid, IntersectionObserver and browser history provide
the requested interactions. The root viewer's existing AKN typography is reused.

Two deliberate adaptations prevent misleading legal presentation:

- The comparison navigates affected **provisions**, because the generated base
  XML has no reliable PDF page mapping. Source drawer links use actual evidence
  page numbers. The UI does not invent page alignment.
- Acceptance changes review status and shows a source citation. It does not
  insert bracket punctuation or invented statutory footnotes into the law.
  Unsupported operations remain conflicts. Example BBMP amendments/rules from
  the video are not fabricated as real data.

| Component | Responsibility |
| --- | --- |
| `webui/workspace.py` | Page routes, catalogue, proposal canvas, visual expression editing, uploads, reader PDF/XML, related documents and issues |
| `webui/static/workspace.js` | Dashboard, timeline, review decisions, visual editing and reader interactions |
| `webui/static/workspace.css` | Admin and reader design, responsive layout and print rules |
| `webui/templates/workspace.html` | Shared application shell and accessible dialogs |
| `webui/review_editor.py` | Protected text segments and existing safe structural operations; text-only schedule containers |
| `scripts/akn_consolidator/service.py` | Existing consolidation, history, validation and approval invariants; compact version summary additions |
| `scripts/akn_consolidator/storage.py` | Existing immutable store plus additive related-document and reader-issue tables |

Workspace endpoints live under `/workspace/api`; the existing
`/consolidation/api` endpoints handle import, extraction, manifest review,
inspection, preview, application, approval and evidence export. The OpenAPI page
lists concrete request schemas. `NYAYA_CONSOLIDATION_DIR` selects the local store;
the default is `consolidation-data/`. Use separate stores for demonstrations and
real review work.

## Verification and limits

Run the full suite and JavaScript syntax check:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD/scripts"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
node --check webui/static/workspace.js
```

Focused tests in `tests/test_visual_workspace.py` cover immutable source text,
protected inline content, revision/hash/evidence gates, stable identifiers,
schedule-cell preservation, repeated correction approval, rejected instructions,
actual First-amendment proposal/application, reader boundaries, generated PDFs,
related PDFs, reader issues, uploads and HTTP route integration. Existing engine,
reference and visual structural-operation tests remain part of the suite.

This remains a trusted local demonstration without accounts, network publication,
government attestation, Kannada editing or OCR. Approvals represent local reviewer
decisions. XML validity cannot establish agreement with the Gazette. Complex
reference reconciliation still uses the detailed instruction desk. Generated
reading PDFs are not Gazette facsimiles. Related documents have no separate
approval lifecycle beyond the reviewed relationship action.

Verification on 2026-10-26: **188 tests passed** (35.47 seconds), and JavaScript
syntax and Git whitespace checks passed. A fresh replay applied all three Teachers
amendments; their comparison canvases rendered 3, 23 and 11 instructions without
conflicts. The reader returned four approved versions and generated the latest
reading PDF. BBMP imported and rendered 1,953 selectable provisions in 0.33 seconds
in-process; this is a server-side smoke measurement, not a browser performance
benchmark. Requests through the assembled application returned HTTP 200 for both
new portals, the retained viewer/consolidation pages and the new static assets.

Browser launch and localhost binding are restricted in the implementation
environment. HTTP/ASGI workflow tests and syntax checks run there, but the visual
browser walkthrough above still needs a local check for rendering, scrolling,
contenteditable interaction, fullscreen and native PDF viewing.

## Handoff log

- 2026-10-26: Created `feature/visual-consolidation-workspace` from
  `feature/amendment-consolidation`; preserved previous demo branches and routes.
- Read the supplied UI plan and inspected frames of the supplied video.
- Connected both portals to the real store and consolidation engine, added the
  visual-to-version bridge, and retained approval/invalidation boundaries.
- Added focused integration tests and startup/walkthrough documentation. The
  workspace-level `brief/RUN_COMMANDS_AND_CONSOLIDATION_DEMO.txt` includes the new
  launch commands alongside the earlier demonstrations.
