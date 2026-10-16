# Visual editor branch

## Findings and implementation

The visual editor prepares one selected provision at a time. Its `heading` and `p` fields appear as editable text spans in the draft comparison column beside the source PDF and original provision. Inline `<ref>`, `<def>`, `<span xml:lang>` and other nested elements appear as shaded protected chips. The client sends the text segments and an operation keyed by the selected `eId`; `webui/review_editor.py` changes only the matching XML text and tails. Paragraphs inside table cells are editable in the same way, while rows and cells stay fixed.

The structural controls add a section after a selected section or add subsections, clauses and provisos inside a supported parent. They also remove, renumber, or move a selected provision. The server rebuilds descendant `eId` prefixes when numbering changes. It blocks changes to referenced provision IDs and collisions, then the shared review route validates the entire assembled Act. Adding a child to a leaf changes its `content` wrapper to `intro` while keeping its legal text and inline elements.

The BBMP outline is loaded once and each provision's editor loads on selection. The PDF, source XML and draft are separate panels. The diff and revision log let the reviewer see exactly what changed before approval.

## Limits

The move control swaps adjacent numbered siblings and their position numbers. Unnumbered provisos cannot be moved with it. The demo handles sections, subsections, simple lettered clauses and provisos; complex inserted labels such as `208A` and clause sequences past `z` require manual XML work. New provisions contain placeholder text that the reviewer must replace. Its validity checks establish XML structure, not correspondence with the gazette. Approval is a local name and UTC timestamp without authentication or publication.

## Test results and handoff

The branch has 145 passing tests with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q`. Focused tests cover protected inline text, table cells, all add controls, renumber, move, remove, incoming reference blocks, revision conflicts, approval reset, XML validity and source isolation. A direct local walkthrough opened `tranfer_of_teachers.xml`, previewed and saved a wording change, validated, approved and wrote the export artifact. Opening `BBMP Act.xml` loaded 1,932 provision entries in about 0.12 seconds; a table cell edit passed validation. A real browser walkthrough could not be completed here because a local listening socket could not be opened.
