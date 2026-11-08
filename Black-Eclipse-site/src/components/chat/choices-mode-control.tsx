"use client";

// ── ChoicesModeControl — the "+" menu's Auto / Choices / Off submenu ─────────
//
// A per-question presentation preference, not a capability grant. It lives in
// the composer's "+" menu (not the toolbar) so it stays out of the way until
// the user opts in. The choice is persisted, so once selected it applies to
// every subsequent run until changed. "On" nudges the model to ask one question
// with clickable options before an ambiguous turn; "Off" suppresses that nudge;
// "Auto" lets the base prompt's act-don't-ask guidance decide. The `clarify`
// tool itself stays read-only and the runtime still bounds one question per
// turn.

import { useEffect, useState } from "react";
import { ListChecks } from "@/lib/icons";
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getChoicesMode,
  setChoicesMode,
  subscribeChoicesMode,
  type ChoicesMode,
} from "@/lib/agent/choices-mode";

/** Short badge shown on the submenu trigger so the active choice is visible. */
function badge(mode: ChoicesMode): string {
  return mode === "on" ? "On" : mode === "off" ? "Off" : "Auto";
}

export function ChoicesModeControl({ disabled = false }: { disabled?: boolean }) {
  const [mode, setMode] = useState<ChoicesMode>("auto");

  useEffect(() => {
    setMode(getChoicesMode());
    return subscribeChoicesMode(setMode);
  }, []);

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger disabled={disabled} title="Choices mode">
        <ListChecks size={15} className="shrink-0" />
        <span>Choices mode</span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {badge(mode)}
        </span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-52">
        <DropdownMenuLabel>Clarifying questions</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={mode}
          onValueChange={(value) => setChoicesMode(value as ChoicesMode)}
          disabled={disabled}
        >
          <DropdownMenuRadioItem value="auto">Auto — only when it matters</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="on">On — every run</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="off">Off — never ask</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
