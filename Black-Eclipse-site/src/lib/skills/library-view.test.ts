import { describe, expect, it } from "vitest";

import {
  DEFAULT_LIBRARY_VIEW,
  libraryHref,
  libraryViewQuery,
  parseLibraryView,
} from "./library-view";

describe("skills library view state", () => {
  it("defaults an empty search", () => {
    expect(parseLibraryView("")).toEqual(DEFAULT_LIBRARY_VIEW);
    expect(parseLibraryView("?")).toEqual(DEFAULT_LIBRARY_VIEW);
  });

  it("round-trips filters and sort", () => {
    const view = {
      query: "earnings call",
      category: "finance",
      status: "enabled",
      risk: "high",
      sort: "risk" as const,
    };
    expect(parseLibraryView(`?${libraryViewQuery(view)}`)).toEqual(view);
  });

  it("omits default values from the URL", () => {
    expect(libraryViewQuery(DEFAULT_LIBRARY_VIEW)).toBe(
      "tab=skills&sub=skills.library",
    );
  });

  it("ignores an unknown sort and keeps the default", () => {
    expect(parseLibraryView("?sort=recent").sort).toBe("name");
  });

  it("accepts the recently-updated sort", () => {
    expect(parseLibraryView("?sort=updated").sort).toBe("updated");
  });

  it("builds a detail href with the focus id and current filters", () => {
    const view = { ...DEFAULT_LIBRARY_VIEW, query: "aapl" };
    expect(libraryViewQuery(view, { subroute: "skills.detail", focus: "finance.market-data" })).toBe(
      "tab=skills&sub=skills.detail&q=aapl&focus=finance.market-data",
    );
  });

  it("emits an absolute href from a base", () => {
    expect(libraryHref(DEFAULT_LIBRARY_VIEW, {}, "/x")).toBe(
      "/x?tab=skills&sub=skills.library",
    );
  });
});
