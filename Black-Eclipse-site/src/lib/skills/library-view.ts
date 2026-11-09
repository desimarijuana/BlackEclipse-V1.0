// ── Skills Library view state in the URL ───────────────────────────────────
// The Skills screen is a keep-alive SPA, so local component state survives tab
// switches but not a reload, a shared link or Ctrl/Cmd-click. This module owns
// the pure parse/serialize pair for the Library's search, filters and sort, and
// for the `skills.detail` drill-down.
//
// URL shape: `/?tab=skills&sub=skills.library&q=…&cat=…&status=…&risk=…&sort=…`
// Detail:    `/?tab=skills&sub=skills.detail&focus=<skillId>&…filters`
//
// The shell strips the `skills.` prefix before dispatching a subroute, and
// passes `focus` through the command store, so `detail` + `focus` is the
// existing, tested route for "open this record".

import { destinationToQuery } from "@/lib/search/deep-link";

export const LIBRARY_SORTS = ["name", "status", "risk", "updated"] as const;
export type LibrarySort = (typeof LIBRARY_SORTS)[number];

export interface LibraryViewState {
  query: string;
  category: string;
  status: string;
  risk: string;
  sort: LibrarySort;
}

export const DEFAULT_LIBRARY_VIEW: LibraryViewState = {
  query: "",
  category: "all",
  status: "all",
  risk: "all",
  sort: "name",
};

function isSort(value: string | null): value is LibrarySort {
  return value !== null && (LIBRARY_SORTS as readonly string[]).includes(value);
}

/** Read the Library view state out of a URL search string. */
export function parseLibraryView(search: string): LibraryViewState {
  const raw = search.startsWith("?") ? search.slice(1) : search;
  let sp: URLSearchParams;
  try {
    sp = new URLSearchParams(raw);
  } catch {
    return { ...DEFAULT_LIBRARY_VIEW };
  }
  const sort = sp.get("sort");
  return {
    query: sp.get("q") ?? "",
    category: sp.get("cat") ?? "all",
    status: sp.get("status") ?? "all",
    risk: sp.get("risk") ?? "all",
    sort: isSort(sort) ? sort : "name",
  };
}

/** Serialize the Library view state into a query string (no leading `?`). */
export function libraryViewQuery(
  view: LibraryViewState,
  opts: { subroute?: string; focus?: string } = {},
): string {
  const params: Record<string, string> = {};
  if (view.query) params.q = view.query;
  if (view.category !== "all") params.cat = view.category;
  if (view.status !== "all") params.status = view.status;
  if (view.risk !== "all") params.risk = view.risk;
  if (view.sort !== "name") params.sort = view.sort;
  if (opts.focus) params.focus = opts.focus;

  return destinationToQuery({
    tab: "skills",
    subroute: opts.subroute ?? "skills.library",
    ...(Object.keys(params).length ? { params } : {}),
  });
}

/** Full href for the Library (or a drill-down) carrying the current filters. */
export function libraryHref(
  view: LibraryViewState,
  opts: { subroute?: string; focus?: string } = {},
  base = "/",
): string {
  return `${base}?${libraryViewQuery(view, opts)}`;
}
