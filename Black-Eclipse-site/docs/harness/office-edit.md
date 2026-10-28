---
title: Office & PDF Editing (preservation-first)
status: Current
last-verified: 2026-10-28
---

# Office & PDF Editing (preservation-first)

**Code:** `python/harness/documents/edit/`
**Tool:** `document_edit`
**Tests:** `python/tests/test_documents_edit.py`

## What it is

Editing an existing Word/Excel/PowerPoint file must not rebuild it. An Office
file is a ZIP of XML parts, and a library round-trip silently drops charts,
pivots, slicers, custom XML, fonts and VBA. This subsystem mutates only the parts
a validated edit plan names, copies every other part from the original bytes,
then proves preservation before publishing.

PDF is different: there is no ZIP package. The default `pypdf` backend rewrites
the file and says `preservationMode: "rewrite"`. If the optional PyMuPDF backend
is installed (`python/requirements-pdf-incremental.txt`, AGPL/commercial), the
edit is written as an incremental update and the report says
`preservationMode: "incremental"`. A missing `pypdf` is an honest
`PDF_LIBRARY_MISSING`; a failed incremental save falls back to the rewrite path
rather than losing the edit.

## Flow

```
source artifact / path
  -> EditPlan.from_dict (closed op allowlist, bounds, one format per plan)
  -> OoxmlPackage.from_bytes (part + ZIP-metadata capture, guards)
  -> docx_ops / xlsx_ops / pptx_ops / pdf_ops
  -> to_bytes (same entry order + metadata; deterministic timestamps optional)
  -> verify_ooxml (untouched-part hashes, relationships, XML, expected text)
  -> ArtifactService.add_version / register_bytes
```

A failed verification raises `EDIT_VERIFICATION_FAILED` and publishes nothing.
The tool accepts an `artifactId` (preferred), a `sessionFile` from the current
conversation's `context`/`output` folder, or a source path.

## Preservation contract

- Every part not named as a target is byte-identical after decompression.
- `[Content_Types].xml`, `.rels`, media, charts, pivots, custom XML and VBA are
  preserved unless an operation explicitly targets them.
- XLSX cell/formula edits remove `xl/calcChain.xml` (when present), update its
  content-type override and workbook relationship, and set
  `calcPr fullCalcOnLoad="1"` / `forceFullCalc="1"`. Those metadata parts are
  reported as targets.
- Digital signatures under `_xmlsignatures/` are not repaired: editing
  invalidates them and the report says so.
- Macro-enabled containers are preserved but never executed. The existing
  document policy (`document_intelligence/security.py`) governs whether a macro
  is accepted at all.
- Encrypted packages, legacy `.doc/.xls/.ppt` and unknown formats are refused;
  convert them first.
- The original artifact is never modified in place. The output is a new artifact
  version (or a new artifact for a path source).

## Production behavior

- **Path sources are confined.** `source`/`path` is accepted only inside the
  active workspace, a trusted root, the current session folder or the artifact
  store. Anything else is `EDIT_SOURCE_DENIED`; prefer `artifactId`/`sessionFile`.
- **Optimistic concurrency.** An artifact edit passes `expectedChecksum` to
  `ArtifactService.add_version`; if another edit landed first, the service refuses
  with `ARTIFACT_CONFLICT` instead of appending over newer bytes.
- **Idempotent retries.** The edit's idempotency key is
  `edit:<artifactId>:<planHash>:<sourceSha>`, so a retried call returns the same
  version rather than creating a duplicate.
- **XML is data, never instructions.** Parts containing `<!DOCTYPE` or `<!ENTITY`
  are refused with `EDIT_XML_UNSAFE`; no DTD/entity expansion is allowed.
- **Macro policy.** A package carrying `vbaProject.bin` is refused with
  `EDIT_MACRO_REFUSED` unless the existing document policy
  (`HARNESS_DOCUMENT_ALLOW_MACROS`) allows macros. A permitted macro is preserved,
  never executed.
- **Telemetry.** Each successful or dry-run edit logs `document.edit` with the
  format, plan hash, source sha256 and targeted parts; the Artifact Center also
  records the version event.
- **Bounded work.** Part count/size, edit count, text length, image size and PDF
  pages are capped. A failed verification publishes nothing.
- **PDF backends are explicit.** `pypdf` is the default rewrite backend; the
  optional PyMuPDF incremental backend is used only when installed, and a failed
  incremental save falls back to the rewrite path rather than losing the edit.

## Operations

| Format | Operations |
|---|---|
| DOCX | `replace_text`, `set_paragraph_text`, `set_table_cell`, `set_core_property`, `insert_image`, `accept_revisions`, `reject_revisions` |
| XLSX | `set_cell`, `set_formula`, `set_number_format`, `rename_sheet`, `append_rows`, `insert_rows`, `delete_rows`, `insert_columns`, `delete_columns` |
| PPTX | `set_slide_title`, `replace_text`, `set_notes`, `set_shape_text`, `delete_slide`, `duplicate_slide`, `replace_chart_data`, `add_smartart_node`, `remove_smartart_node`, `set_smartart_node_text`, `set_smartart_layout` |
| PDF | `fill_form`, `rotate_pages`, `add_annotation`, `set_metadata`, `redact` |

`replace_text` works across runs: it preserves the first run's formatting,
clears intermediate run text and writes the replacement once. On PPTX it also
scans `ppt/diagrams/data*.xml` by default, so SmartArt label text can be changed
without touching the diagram's node structure. `xlsx.rename_sheet` refuses when
another sheet's formula references the old name.

Structural XLSX edits (`insert_rows`/`delete_rows`/`insert_columns`/
`delete_columns`) rewrite A1 references across the workbook: formulas, defined
names, merged ranges, conditional formats, data validations, hyperlinks,
auto-filters, column ranges, table references, table formulas and chart series
formulas are shifted/expanded with the cells. Pivot table locations and cache source ranges are shifted and the cache is marked
`refreshOnLoad`; OLE and legacy VML anchors shift with the rows/columns. Pivot
caches whose definition is missing are refused (`EDIT_PIVOT_UNSAFE`). Structural targets are reported, so the
preservation proof names exactly which parts changed.

`docx.insert_image` adds the media part, image relationship, content-type default
and DrawingML inline shape. `docx.accept_revisions`/`reject_revisions` resolve
tracked insert/delete/move markup deterministically.

`pptx.duplicate_slide` copies the slide part and its relationships, including a
new notes part; `pptx.delete_slide` removes the slide, its relationships and its
notes, and refuses to leave the deck with zero slides. `pptx.replace_chart_data`
replaces an embedded chart's categories and series caches while preserving its
type, axes and styling; supplying more series than the chart owns is refused.
`pptx.add_smartart_node` / `remove_smartart_node` add or prune a node and its
`parOf` connections (the root cannot be removed), and `set_smartart_node_text`
targets one node by `modelId`; `pptx.replace_text` remains the bulk label edit.

`pdf.redact` removes the covered text objects. With the optional PyMuPDF backend
it applies a true redaction inside an incremental update
(`redactionMode: "incremental_true_removal"`, original objects/xref preserved).
Without it, the page is rasterized and replaced, so the text is also gone but the
page becomes an image (`redactionMode: "rasterized_page"`).

## What is deliberately not supported yet

SmartArt layout templates can be swapped from a donor diagram in the same deck;
cross-deck template import is not supported. Pivot definitions with no reachable
cache are refused rather than guessed.

## Failure codes

| Code | Meaning |
|---|---|
| `EDIT_SOURCE_DENIED` | path is outside every authorized root |
| `EDIT_SOURCE_NOT_FOUND` | the artifact/session/path does not exist |
| `EDIT_FORMAT_UNSUPPORTED` / `EDIT_FORMAT_MISMATCH` | not an editable format, or plan/source disagree |
| `EDIT_MACRO_REFUSED` | VBA project present and macro policy is off |
| `EDIT_XML_UNSAFE` | DTD/entity declaration in a package part |
| `EDIT_PIVOT_UNSAFE` | pivot definition/cache cannot be shifted safely |
| `EDIT_DIAGRAM_LAYOUT_MISSING` | SmartArt layout/quick-style/colors relationship missing |
| `EDIT_STRUCTURE_UNSAFE` | structural edit reached an unsupported structure |
| `EDIT_CHART_SERIES_MISMATCH` | chart series count differs from the plan |
| `EDIT_NO_REVISIONS` | accept/reject found no tracked revisions |
| `EDIT_VERIFICATION_FAILED` | untouched-part/relationship/expected-content proof failed |
| `ARTIFACT_CONFLICT` | the artifact changed after it was read |
| `PDF_LIBRARY_MISSING` | pypdf is not installed |

## Honesty and security

- The model emits data, never XML or code; the operation list is closed.
- The read path reuses the existing ZIP/XML guards (part count, part size,
  total size, encryption, duplicate names, path traversal).
- Verification is a gate, not a caption: a report with `ok: false` cannot publish.
- `document_edit` writes only into the confined artifact store. It does not
  accept a storage key and does not run a macro or a shell.
