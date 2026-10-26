# Amendment stitching and versioned review

This engine extends NyayaBandhu with deterministic amendment instructions, human review gates, immutable dated XML expressions, and a local CMS API. It operates separately from PDF conversion and the visual editor. `out/` and `data/` are never edited.

The local review workspace is at `/consolidation` in the existing viewer. It uses the engine and CMS API below. Accounts and publication remain future work. Indigo supplied the conceptual distinction between a work, its dated expressions, and editorial work; no Indigo code or Django application is incorporated.

## Browser review workflow

Run `.venv/bin/python webui/run.py` and open `http://127.0.0.1:8000/consolidation`. The ordinary document viewer also links to the workspace. Set `NYAYA_CONSOLIDATION_DIR` before starting the viewer to select a different local store. For the scripted demonstration, point it to `consolidation-data/teachers-demo`.

1. Enter a reviewer name and reason in the header. Under **Sources**, import a generated English base XML and its gazette PDF. Open both originals from the source card.
2. Under **Versions**, read and inspect the base snapshot, then approve its exact XML hash. Its initial date is the source expression date; the interface does not infer commencement.
3. Import an amending Act under **Sources** and extract candidate instructions. Under **Instructions**, compare each immutable quotation and PDF page with the base target. The PDF pane follows the selected instruction; the original amendment XML is available on demand.
4. Confirm the principal Act identity, effective date, evidence, and instrument order. For each instruction, inspect the target after earlier accepted instructions, review exact matches and incoming references, bind its target hash and match inventory, record any wording or reference decision, and mark it accepted. Structural provision wording and schedule rows have form controls. Complex selectors and decisions can be edited as JSON in the advanced panels. Save a review revision.
5. Under **Preview & apply**, choose the approved predecessor and legal date. Inspect every before/after change, conflicts, XSD validation, and XML diff. Save a draft only after a valid preview.
6. Under **Versions**, read the resulting Act, inspect its XML and hash, compare versions, approve, and download the evidence ZIP. The timeline marks stale expressions. It also supports dated lookup and an explicitly sourced editorial correction.

The workspace shows unsaved edits and requires the current work revision on every mutation. If another tab changes the work, refresh and repeat the preview or review before applying. Each amendment must be reviewed against its PDF; the checked-in fixtures are illustrative decisions, not legal approval.

## Run the Teachers Act demonstration

From the repository root, with the existing virtual environment:

```bash
PYTHONPATH=scripts .venv/bin/python scripts/consolidation_demo.py
```

This replays the checked-in **test decisions** for all three amendments, validates each complete batch, records approvals under a fixture persona, and writes `consolidation-data/teachers-demo/teachers-demo.zip`. Use `--store /path/to/a/new/directory` for a second run; it never resets a store. Test approvals are not lawyer attestation.

The demonstration covers 37 instruction candidates: 32 textual/structural changes and five classified commencement or repeal/savings effects. Each candidate retains its amendment section, original quotation, and PDF pages. See [review decisions](fixture-decisions.md) before relying on the results.

## Normal review workflow

```bash
# Editable installation adds akn-consolidate; no new runtime dependencies.
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
.venv/bin/akn-consolidate --help
```

Without installation, use `PYTHONPATH=scripts .venv/bin/python -m akn_consolidator` in place of `akn-consolidate`.

1. `import --kind base --xml ... --pdf ... --actor ... --reason ...` snapshots both sources and creates an unapproved as-published expression. It returns the work ID, revision, expression ID, and XML hash.
2. `approve EXPRESSION --revision N --xml-hash HASH --actor ... --reason ...` records review of that exact base snapshot. Its initial date is the source expression/publication date, **not a finding of legal commencement**.
3. `import --kind amendment --work WORK --revision N --xml ... --pdf ... --actor ... --reason ...` registers an instrument against the work.
4. `extract SOURCE --revision N --actor ... --reason ...` returns a candidate manifest. It is always pending review; no extracted instruction is automatically accepted.
5. Save the returned `manifest.body` to JSON. Confirm principal Act identity, commencement evidence, amendment sequence, targets, matches, and each operation. Use `inventory EXPRESSION --target '{"eid":"sec_2__cl_i"}' --old Schedule` to inspect matches in a stored expression. The browser's **Inspect staged target** action and `POST /manifests/{id}/inspect` replay earlier accepted instructions when a later target changes within the same amendment.
6. `review MANIFEST --file reviewed.json --revision N --manifest-revision M --actor ... --reason ...` appends an instruction revision. Use the returned work revision for the next mutation.
7. `preview WORK --parent EXPRESSION --date YYYY-MM-DD` reports exact text changes, an XML diff, conflicts, validation, identities, and a preview hash. No expression is saved. Inspect the original PDF and source XML as well as this report.
8. `apply WORK --parent EXPRESSION --date YYYY-MM-DD --revision N --preview-hash HASH --actor ... --reason ...` reruns that preview and saves a **draft** only if the entire batch passes.
9. Inspect the draft with `xml EXPRESSION --output draft.xml` and `diff LEFT RIGHT`. Approve its exact XML hash, then `export EXPRESSION --output review.zip`.

`history WORK` returns sources, current manifests, expressions, and append-only events. `lookup WORK --date YYYY-MM-DD [--known-at TIMESTAMP]` separates legal dates from editorial knowledge. The timezone-qualified timestamp limits approval, source discovery, instruction revisions, and invalidation to what was known then. The result reports unresolved registered sources and explicitly makes no claim about undiscovered instruments.

`correct EXPRESSION --file correction.json --revision N --actor ... --reason ...` accepts `{ "operations": [...], "evidence": {"source_id":"...", "pdf_pages":[10], "quote":"..."} }`. It creates a separately sourced editorial correction at the same effective date. Its approval supersedes that expression and invalidates downstream versions; it does not masquerade as a statutory amendment.

## CMS API

Start the existing viewer with `.venv/bin/python webui/run.py`. Routes are registered in its FastAPI application; visit `/docs` for request schemas. Set `NYAYA_CONSOLIDATION_DIR` to choose the store (default `consolidation-data/visual-workspace` on the combined visual branch). To inspect the scripted demo through this API, set it to `consolidation-data/teachers-demo`.

| Method | `/consolidation/api` path | Use |
| --- | --- | --- |
| GET | `/works` | Work catalogue and current revision |
| POST | `/sources` | Import paths relative to `out/` and `data/` |
| GET | `/sources/{id}/pdf` or `/xml` | Immutable gazette or generated source |
| POST | `/sources/{id}/extract` | Candidate instruction manifest |
| POST | `/manifests/{id}/review` | Save reviewed manifest body and revision |
| POST | `/works/{id}/preview` | Conflict and change review |
| POST | `/works/{id}/apply` | Save a valid draft tied to a preview |
| POST | `/expressions/{id}/inventory` | Exact occurrence inventory and target hash |
| POST | `/expressions/{id}/approve` | Approve exact XML hash |
| POST | `/expressions/{id}/correct` | Draft an evidenced editorial correction |
| GET | `/works/{id}/history` | Timeline and audit trail |
| GET | `/works/{id}/workspace` | Compact CMS timeline and current manifests |
| GET | `/catalog` | Available local XML/PDF sources |
| POST | `/manifests/{id}/inspect` | Staged target, matches, references, and provision picker |
| GET | `/works/{id}/lookup?as_of=...&known_at=...` | Dated expression and coverage |
| GET | `/expressions/{id}` | Full expression record |
| GET | `/expressions/{id}/xml` | Inspect draft/historical XML, without approval claim |
| GET | `/expressions/{id}/export` | Approved XML and provenance ZIP |
| GET | `/diff?left=...&right=...` | XML version comparison |

All mutations require an actor and reason. Mutations to an existing work require its latest `revision`; manifest review additionally requires `manifest_revision`. Conflicts return HTTP 409; invalid input returns 400 or request-schema 422. Imports are restricted to repository source/output paths. This is the existing trusted-local viewer model, without authentication or deployment hardening.

The readable Act view is `/consolidation/read/{expression_id}`. It labels draft, approved, and stale expressions and uses the existing Akoma Ntoso renderer.

## Further reading

- [Architecture and storage](architecture.md)
- [Instruction format and transformation rules](instructions.md)
- [Corpus decisions and remaining limits](fixture-decisions.md)
- [Verification and handoff](handoff.md)
