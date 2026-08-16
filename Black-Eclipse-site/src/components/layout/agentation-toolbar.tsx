"use client";

import { Agentation } from "agentation";

/**
 * Client-only wrapper for the Agentation visual feedback toolbar.
 * Rendered once at the root so users can click any element, add a note,
 * and copy structured selectors for the AI agent to act on.
 */
export function AgentationToolbar() {
  return <Agentation />;
}
