"use client";

// ── PlanModeControl — the "+" menu's Auto / Plan / Off submenu ───────────────
//
// A per-question presentation preference, not a capability grant. It lives in
// the composer's "+" menu (not the toolbar) so it stays out of the way until
// the user opts in. The choice is persisted, so once selected it applies to
// every subsequent run until changed. "On" tells the model to lay out a plan
// and wait for approval before it starts the work; "Off" suppresses that nudge;
// "Auto" lets the base guidance decide. It never hard-blocks a tool call.

import { useEffect, useState } from "react";
import { Waypoints } from "@/lib/icons";
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getPlanMode,
  setPlanMode,
  subscribePlanMode,
  type PlanMode,
} from "@/lib/agent/plan-mode";

/** Short badge shown on the submenu trigger so the active choice is visible. */
function badge(mode: PlanMode): string {
  return mode === "on" ? "On" : mode === "off" ? "Off" : "Auto";
}

export function PlanModeControl({ disabled = false }: { disabled?: boolean }) {
  const [mode, setMode] = useState<PlanMode>("auto");

  useEffect(() => {
    setMode(getPlanMode());
    return subscribePlanMode(setMode);
  }, []);

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger disabled={disabled} title="Plan mode">
        <Waypoints size={15} className="shrink-0" />
        <span>Plan mode</span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {badge(mode)}
        </span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-56">
        <DropdownMenuRadioGroup
          value={mode}
          onValueChange={(value) => setPlanMode(value as PlanMode)}
          disabled={disabled}
        >
          {/* GroupLabel must live inside a Group/RadioGroup or Base UI throws
              "MenuGroupContext is missing" when the submenu mounts. */}
          <DropdownMenuLabel>Plan before acting</DropdownMenuLabel>
          <DropdownMenuRadioItem value="auto">Auto — plan when it helps</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="on">On — plan, then wait</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="off">Off — act without a plan</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
