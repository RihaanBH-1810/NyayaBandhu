# Instruction manifest v1

Extraction returns a record with `id`, `revision`, and `body`. Review submits the **body**, preserving the immutable source fields. Work revision and manifest revision are supplied separately to the service or API.

```json
{
  "format_version": 1,
  "source_id": "immutable-source-id",
  "source_work_uri": "/akn/in-ka/act/2021-10-01/27",
  "target_identity": {"jurisdiction":"in-ka", "number":"4", "year":"2020"},
  "identity_confirmed": true,
  "effective_date": "2021-04-29",
  "date_confirmed": true,
  "date_evidence": "Recorded determination, with source provision",
  "sequence": 1,
  "coverage": [{"source_eid":"sec_2", "heading":"Amendment of section 10", "pdf_pages":[3]}],
  "operations": [{
    "id": "sec_2_op_1",
    "review_status": "accepted",
    "source": {"source_eid":"sec_2", "pdf_pages":[3], "quote":"Original full source instruction"},
    "action": "insert_provision",
    "target": {"path":[["section","10"],["subsection","5"]]},
    "position": "after",
    "fragments": [{"tag":"subsection", "num":"(6)", "text":"Reviewed replacement text"}]
  }]
}
```

The example shows the shape, not a complete real instruction or page determination. Actual corpus manifests are in `tests/fixtures/consolidation/reviews.json`.

## Review contract

`format_version`, source identity/URI, section coverage, and original operation provenance cannot be changed. Existing operation IDs cannot be deleted. An instruction with a separate legal effect can be classified as `effect`, retaining its evidence. New operations must identify an already covered source section. Accepted instructions need PDF pages within the source document and a quotation. A manifest becomes ready only after identity/date confirmation, date evidence, and acceptance of every operation; `blocked` candidates never become ready.

Review may correct targets, payloads, or interpretations, with actor/reason recorded on the manifest revision. Add `review_note` for operation-specific decisions. A textual operation's `old` field may differ from the immutable source quotation only through an explicit reviewer decision, as in the corpus's wording mismatches. Extraction never makes that correction itself.

## Targets and preconditions

Select exactly one target using:

- `{"eid":"sec_10__subsec_1__cl_vi"}`;
- `{"path":[["section","10"],["subsection","1"],["clause","vi"]]}`;
- `{"region":"act"}`, `longTitle`, or `preamble`;
- `{"region":"schedule", "label":"SCHEDULE-I"}`.

A proviso path uses its current ordinal position, e.g. `["proviso","3"]`. Printed-number normalization strips numbering punctuation; text matching does not ignore case or silently correct words. Ambiguous targets fail.

Optional `expected_hash` binds the canonical target subtree, and `target_identity` binds its stable identity. These refer to the **intermediate tree immediately before the operation**. The corpus fixtures bind every changed target with a hash. Exact-match counts, reference preconditions, and the approved preview independently bind transformations to their inputs.

## Supported operations

| Action | Required edit fields / behavior |
| --- | --- |
| `text_replace` | `old`, `new`, positive exact `count`; operates in text-bearing fields |
| `text_insert` | `old` anchor, `new` text including desired spacing, `position` before/after, `count` |
| `text_omit` | `old`, `count`; optional explicit inline removal decisions |
| `slot_edits` | `edits`: exact `eid`, `slot` text/tail, `before`, `after`; no flattening |
| `insert_provision` | `fragment` or `fragments`, position before/after/last_child |
| `replace_provision` | `fragment`; same printed root number, new descendant identities |
| `omit_provision` | Delete target and retain identity tombstones |
| `renumber` | `new_number`, explicit incoming reference decisions |
| `schedule_add` | Schedule `hcontainer` fragment and an existing schedule metadata template |
| `table_insert` | `after_group`, `rows`; append after the uniquely identified final roman-numbered group |
| `effect` | `classification` and source evidence; no change to the consolidated text |
| `blocked` | `issue`; needs further interpretation before application |

Fragments support sections, subsections, clauses, subclauses, provisos, and schedule containers, with `num`, `heading`, `subheading`, `text`, and nested `children`. Schedule `table` is a list of rows of cell strings. Replacing or inserting tables beyond the demonstrated patterns requires explicit supported structure, not an arbitrary XML string.

## Text and inline structure

Matching uses exact case-sensitive text with reversible whitespace normalization. `whole_word: true` prevents substring matches (e.g. `ratio` inside `rationalisation`). Each match records field, offset, actual text, and whether it affects protected inline content or crosses element boundaries.

Whole-Act replacements require `global: true`, an exact `occurrences` list, and an exact count. Protected inline text additionally requires `allow_protected: true`. Ordinary text edits change a single text/tail slot and retain surrounding references, definitions, and language spans. A cross-inline match is blocked unless resolved through exact slot edits or an explicitly approved inline omission.

For the Third amendment, omission of `and (vii)` explicitly identifies the removable `<ref>`:

```json
{
  "inline_removals": [{
    "eid":"sec_10__subsec_4__content__p_1__ref_2",
    "href":"#sec_10__subsec_1__cl_vii",
    "text":"(vii)"
  }],
  "allow_protected": true,
  "occurrences": ["use the actual inventory objects, not this placeholder"]
}
```

The entire reference text must be within the omission, its href/text must match, and no other protected inline node may be affected. Its tail survives. The earlier provision omission records `reference_updates` with `eid`, `old_href`, `old_text`, and `resolved_by: "sec_6_op_3"`. The engine requires that exact later operation in the same atomic batch. Renumbering instead records `new_href` and `new_text`. There is no implicit reference retargeting based on nearby numbers.

## Validation and approvals

Every assembled expression passes the existing OASIS XSD, eId syntax/uniqueness, reference, and language checks. Metadata is updated and checked again. Validation does not establish that the gazette wording, commencement, or legal interpretation is correct. Those determinations belong in the review record.
