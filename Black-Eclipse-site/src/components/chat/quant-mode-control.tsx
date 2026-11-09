"use client";

// ── QuantModeControl — the "+" menu's Auto / Quant / Off submenu ──────────────
//
// A per-question presentation preference, not a capability grant. It lives in
// the composer's "+" menu (not the toolbar) so it stays out of the way until
// the user opts in. The choice is persisted, so once selected it applies to
// every subsequent run until changed. "On" opts the turn into the quant
// protocol; "Off" suppresses it; "Auto" lets the runtime's deterministic
// classifier decide. The server validates the value, and the Python quant
// layer still grants nothing it did not already have.

import { useEffect, useState } from "react";
import { FlaskConical } from "@/lib/icons";
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getQuantMode,
  setQuantMode,
  subscribeQuantMode,
  type QuantMode,
} from "@/lib/agent/quant-mode";

/** Short badge shown on the submenu trigger so the active choice is visible. */
function badge(mode: QuantMode): string {
  return mode === "on" ? "On" : mode === "off" ? "Off" : "Auto";
}

export function QuantModeControl({ disabled = false }: { disabled?: boolean }) {
  const [mode, setMode] = useState<QuantMode>("auto");

  useEffect(() => {
    setMode(getQuantMode());
    return subscribeQuantMode(setMode);
  }, []);

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger disabled={disabled} title="Quant mode">
        <FlaskConical size={15} className="shrink-0" />
        <span>Quant mode</span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {badge(mode)}
        </span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-52">
        <DropdownMenuRadioGroup
          value={mode}
          onValueChange={(value) => setQuantMode(value as QuantMode)}
          disabled={disabled}
        >
          {/* GroupLabel must live inside a Group/RadioGroup or Base UI throws
              "MenuGroupContext is missing" when the submenu mounts. */}
          <DropdownMenuLabel>Quant protocol</DropdownMenuLabel>
          <DropdownMenuRadioItem value="auto">Auto — classifier decides</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="on">On — every run</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="off">Off — never add it</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
