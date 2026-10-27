---
title: Overview — Graph Studio Workspace
status: Current
last-verified: 2026-10-26
---

# Overview

**What this is:** the ONE Graph-mode page. It hosts the whole Graph Studio
workspace: the workflow gallery (view/open/create) and, once a workflow is
opened, the editor. The old separate `graph-studio` nav page was retired;
Overview is the entry point.

## Behavior

- Lists saved workflows as a searchable card gallery (name, description,
  version, tags, updated time) plus the template starter set.
- **New workflow** and **Generate from prompt** create a workflow and open the
  editor in place (`catalog.open`/`createFrom*` load the IR and bump `loadNonce`).
- Opening a card loads that workflow and switches the page to the editor.
- **Continue editing** reopens the workflow already held in the editor.
- The editor's **Workflows** back action returns to the gallery. Old
  `?tab=graph-studio` links alias to Overview.
- It never edits workflow semantics itself: the gallery is a view over the
  shared `catalog-store`, and the editor remains the single authoring surface.

## Where it lives

| Layer | File |
| --- | --- |
| Page | `src/components/screens/overview/overview-screen.tsx` (wraps `graph-studio/graph-studio-screen.tsx`) |
| Gallery | `src/components/screens/graph-studio/graph-home.tsx` |
| Workflow store | `src/lib/graph-studio/catalog-store.ts` |
| Nav | `overview` AppTab + `src/lib/sidebar/config.ts` (group `graph`, Graph mode only) |
| Shell mount | `src/components/screens/stock-chat.tsx` (keep-alive tab; `graph-studio` deep links alias here) |

The page is a keep-alive SPA tab like the other Screens; it owns no server state
beyond the workflow catalog calls.
