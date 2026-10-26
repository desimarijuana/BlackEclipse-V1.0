---
title: Tables — Spreadsheet Data Store
status: Current
last-verified: 2026-10-26
---

# Tables

**What this is:** the top-level **Tables** page — spreadsheet-style tables the
operator can create, fill and edit (the n8n Data Tables equivalent). It is the
place for user-authored rows, separate from connector-fed datasets and from the
canonical market tables.

## Why it exists

Chat, the agent and Graph Studio all need somewhere to put structured scratch
data. Connector-fed `CustomDataset` rows are read-only from the UI and require a
connector schema. Tables adds a first-class editable surface: define columns once,
then add/rename/delete columns and rows like a spreadsheet.

## What it does

- **Create** a table with a name, optional description and typed columns
  (`string`, `number`, `boolean`, `date`, `json`).
- **Edit cells** in place. Text/number/date/JSON cells save on blur; booleans save
  immediately. Cells are stored as JSON row values keyed by column id.
- **Manage columns** — rename inline, add a column, delete a column. Deleting a
  column stops displaying its cells (values remain in stored rows).
- **Manage rows** — add a row, delete a row, search across visible cells.
- **Rename/delete** the table itself.
- **Never fabricates data.** Empty cells are empty; API failures show the error.

Connector-fed datasets remain in **Settings → Market Data → Custom data sources**
(`docs/NAVIGATION.md`). Tables is not a second market-data path.

## Storage and bounds

`DataTable` and `DataTableRow` in `prisma/schema.prisma` (JDDS/SQLite). Both
structured fields are JSON strings because Prisma + SQLite has no Json column in
this project:

| Field | Shape |
| --- | --- |
| `DataTable.columns` | `TableColumn[]` = `{ id, name, type }` (max 60 columns) |
| `DataTableRow.values` | `Record<columnId, unknown>` (row JSON capped at 1 MB) |

Rows belong to a table (`onDelete: Cascade`). Row edits explicitly bump the
table's `updatedAt` so the list reflects recent changes.

## Where it lives

| Layer | File |
| --- | --- |
| Page | `src/components/screens/tables/tables-screen.tsx` |
| Grid / create dialog | `table-grid.tsx`, `create-table-dialog.tsx` |
| Types / client | `src/lib/tables/types.ts`, `src/lib/tables/client.ts` |
| Server store | `src/lib/tables/store.ts` |
| API | `src/app/api/tables/route.ts` (list/create), `src/app/api/tables/[id]/route.ts` (read, `update_meta` / `update_columns` / `add_row` / `update_row` / `delete_row`, delete) |
| Nav | `tables` AppTab + `src/lib/sidebar/config.ts` (group `both`, standard nav list) |
