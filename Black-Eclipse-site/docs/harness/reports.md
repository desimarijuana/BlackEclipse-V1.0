---
title: Reports (PDF, Word, Excel and computed deliverables)
status: Current
last-verified: 2026-10-19
---

# Reports

**Who this is for:** anyone changing how Eclipse turns a computed result into a
downloadable report, or debugging a report that failed to render.

## What it does

`eclipse_report` assembles a report from neutral content blocks and saves the
real file in the Artifact Center. It is the reporting surface for a computed
result: the agent writes the values it actually computed, labels them computed,
and never substitutes a retrieved figure for a derived one.

Supported formats:

| Format | Writer |
|---|---|
| `pdf` | `documents/reporting.py::build_pdf` — paginated Matplotlib PDF backend (vendored, no new dependency). |
| `docx` | `documents/authoring.py::build_docx` (`python-docx`). |
| `xlsx` | `documents/authoring.py::build_xlsx` (`openpyxl`). |
| `pptx` | `documents/authoring.py::build_pptx` (`python-pptx`). |
| `markdown` / `md` / `txt` | `documents/authoring.py` text builders. |

## Flow

```
analysis_run (compute; returns outputs + provenance)
  -> eclipse_report(format="pdf", title=..., blocks=[...])
  -> Artifact Center record (real bytes, preview/download)
```

For a reusable report, build a `report_template` capability through the
Capability Builder; the recipe computes the values, then `eclipse_report`
renders them.

## Block vocabulary

- `heading` (`text`, `level` 1–3)
- `paragraph` (`text`)
- `bullets` / `numbers` (`items`)
- `table` (`headers`, `rows`)
- `page_break`

PDF pages are paginated automatically; tables are bounded and long cell text is
truncated. Word/Excel/PowerPoint use the existing authoring builders, so their
content rules are unchanged.

## Artifact and honesty rules

- Bytes are registered through the ONE `ArtifactService.register_bytes` with
  `source_tool="eclipse_report"`; the file appears in the Artifact Center.
- A missing writer library, an unrenderable format, or an unavailable artifact
  store returns a coded error (`DOCUMENT_LIBRARY_MISSING`,
  `REPORT_RENDER_UNAVAILABLE`, `REPORT_RENDER_FAILED`, `ARTIFACT_UNAVAILABLE`) — never a fake file.
- A computed value in a report is labelled computed; the tool cannot verify the
  provenance of a number it is given, so the agent must supply the computed
  result and its method.
- No network, no arbitrary filesystem path, no macro execution.

## Tests

`python/tests/test_reports.py` covers real PDF bytes, docx/xlsx dispatch,
artifact registration, empty-report refusal and unsupported-format refusal.
`python/tests/test_documents_authoring.py` covers the existing builders.

## Not yet implemented

- Embedded report figures (the analysis figure is already an Artifact Center
  image; a future block can place it directly on a PDF page).
- HTML/PDF styling templates and PDF/A.
- A report-template UI (the capability appears in Capability Studio › Generated).
