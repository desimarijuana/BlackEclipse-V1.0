---
title: Agentic Overview — Workflow Dashboard
status: Current
last-verified: 2026-10-26
---

# Agentic Overview

**What this is:** the Agentic-mode landing page. It is the workflow gallery
(view/open/create) without the Graph Studio editor chrome.

## Behavior

- Lists saved workflows as the same searchable card gallery Graph Studio uses
  (name, description, version, tags, updated time).
- **New workflow** and **Generate from prompt** create a workflow and route to
  the Graph Studio tab; Graph Studio's editor opens automatically because
  `catalog.open`/`createFrom*` load the IR and bump the editor's `loadNonce`.
- **Continue editing** reopens the workflow already held in the editor.
- Templates are available in the same gallery.
- It never edits workflow semantics itself: the gallery is a view over the
  shared `catalog-store`, and the editor remains the single authoring surface.

## Where it lives

| Layer | File |
| --- | --- |
| Page | `src/components/screens/overview/overview-screen.tsx` (thin wrapper over `graph-studio/graph-home.tsx`) |
| Workflow store | `src/lib/graph-studio/catalog-store.ts` |
| Nav | `overview` AppTab + `src/lib/sidebar/config.ts` (group `agentic`, first agent item) |
| Shell mount | `src/components/screens/stock-chat.tsx` (`onOpenWorkflow` switches to `graph-studio`) |

The page is a keep-alive SPA tab like the other Screens; it owns no server state
beyond the workflow catalog calls.
