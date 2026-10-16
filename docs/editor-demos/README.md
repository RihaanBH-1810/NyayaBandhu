# Local lawyer review demos

The demos begin at commit `50b96a5` and live on `demo/bluebell-editor` and `demo/visual-editor`. The base XML under `out/base_act/eng/` is read only. Open the viewer's document list and choose **Review** beside the Teachers Transfer Act or BBMP Act. The first visit snapshots that XML in `review-data/<editor>/`, which is gitignored. A source hash identifies the draft, so converting the Act again starts a separate review without destroying the earlier one. The two editor branches keep separate local drafts.

## Architecture and decisions

`webui/review.py` owns local draft state, source snapshots, numbered XML revisions, validation, approval and export. The branch-specific `webui/review_editor.py` implements `prepare` and `edit`. The browser loads the provision list once and a selected provision on demand, so the BBMP Act does not put every section's editor in the initial HTML. Revision numbers are required on save and approval. The application keeps a process lock for its local writes and uses atomic file replacement. It has no accounts; the approval name is supplied by the reviewer.

The original XML and source PDF remain accessible for comparison. The PDF lookup uses the source XML filename's stem. Every saved revision passes the existing `Validator` with the AKN XSD, identifier, reference, and language checks. The review app does not modify `out/` and does not consolidate amendments or attest publication.

## Demo script

1. Run `.venv/bin/python webui/run.py` and open `http://127.0.0.1:8000`.
2. Choose **Review** for `tranfer_of_teachers.xml`; select a section from the left.
3. Compare the Gazette PDF, untouched XML, and rendered draft; edit and preview, then save.
4. Inspect the XML diff and validation report. Enter a reviewer name, approve and download XML.
5. Edit again to see the status return to draft and export close until another approval.
6. Repeat on `BBMP Act.xml`; filter provisions to test navigation.

## Test and handoff log

- Baseline at `50b96a5`: 134 tests pass with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q`.
- Both existing generated sample Acts pass the XSD, identifier, reference and language checks.
- The reviewer must still compare each legal word with the gazette. XML validity alone does not establish textual accuracy.
