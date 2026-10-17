# Verification and handoff log

## Implementation

- Branch: `feature/amendment-consolidation`, based on the existing `demo/visual-editor` branch (`664aacb`). Existing review features remain available.
- New package: `scripts/akn_consolidator/`; CLI entry point: `akn-consolidate` / `python -m akn_consolidator`.
- Local CMS API: `webui/consolidation.py`, included by the existing viewer app.
- Demonstration: `scripts/consolidation_demo.py`; explicit reviewed manifests and expected snapshots in `tests/fixtures/consolidation/`.
- Project brief and local Indigo checkout were inspected for workflow context. No Indigo implementation code is copied, and no Bluebell/Indigo dependency is added.

## Verification

Run from the repository root:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q
```

Baseline: **145 tests passed** before consolidation changes. Final suite: **170 tests passed**, including 25 consolidation tests.

Coverage includes:

- Full First → Second → Third Teachers Act chain, frozen expected XML, PDF/source hashes, 37 instruction coverage, 32 passive modification records, and semantic checks for inserted, renumbered, replaced, and deleted provisions.
- Preservation of tested untouched sections, inline references, and all existing language spans; stable identities through renumbering; deletion tombstones.
- Exact wording/whitespace matches, whole-word boundaries, protected/global occurrence inventories, source mismatch blocking, and linked deletion of a provision and inline reference in one batch.
- Failed application isolation; stale revisions/previews; duplicate application and duplicate instrument import; hash-bound approval; unapproved/stale export rejection; source corruption detection.
- Two concurrent writers using separate SQLite connections, partial commencement, same-date ordering conflicts, late discovery of earlier instructions, manifest revision invalidation, and historic known-at queries.
- Editorial corrections, store reopen, deterministic ZIP contents and original sources, CLI smoke checks, API input/path/conflict handling, and in-process ASGI route dispatch.

The existing FastAPI application's OpenAPI document includes 15 consolidation paths. API dispatch was verified without opening a listening socket. This restricted execution environment does not reliably wake asyncio from worker threads, so the ASGI test keeps a timer running; the application itself has no testing-specific dispatch changes. A manual browser walkthrough of a dedicated consolidation CMS was not performed; this delivery is the CLI/API phase.

The full demonstration was executed successfully at `consolidation-data/teachers-demo/`, producing `teachers-demo.zip`. This directory is gitignored and contains **fixture-persona approvals**, not legal attestation. Its source data was not modified.

Module CLI execution is verified. Editable installation was attempted with `--no-deps --no-build-isolation`, but the supplied virtual environment lacks `setuptools.build_meta`. No network dependency installation was attempted. Use the documented `PYTHONPATH=scripts` command in this environment, or install the build prerequisites in a normal development environment before the editable install.

## Handoff decisions

1. Keep consolidation separate from conversion and visual editing; reuse the existing XSD/identifier/reference/language validator.
2. Use SQLite plus hashed immutable artifacts for CMS revisions, with Git for implementation and fixtures.
3. Treat extraction as a review proposal. Resolve wording and commencement explicitly, preserving original evidence in every instruction revision.
4. Apply the next effective-date batch atomically. Preview binds the exact inputs; approval replays current instruction coverage before accepting exact XML.
5. Preserve work identity, dated expressions, provision identities, and all historical artifacts. Revisions stale dependent versions and require explicit rebuild/reapproval.
6. Surface the complete workflow through CLI and API now. Build the lawyer-facing CMS on these contracts in the next phase.

## Next CMS phase

A future review screen should show the source PDF, source XML, instruction quotation, target provision and exact occurrences, preview diff, validation conflicts, and effective-date timeline. It should always send the work revision, display incomplete source coverage, and distinguish fixture/draft/stale/approved versions. Accounts, independent approval roles, deployment security, source discovery, additional instruction grammars, and annotation of newly introduced citations remain outside this local engine phase.
