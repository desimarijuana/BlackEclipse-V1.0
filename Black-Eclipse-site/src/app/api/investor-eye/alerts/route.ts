import { NextResponse } from "next/server";
import { getConfigJSON, setConfigJSON } from "@/lib/settings";
import { guardMutation } from "@/lib/api-guard";
import {
  ALERT_RULES_KEY, MAX_RULES, evaluateRules, parseRule,
  type EventAlertRule,
} from "@/lib/investor-eye/alert-rules";
import { assembleState } from "@/lib/investor-eye/state";

export const dynamic = "force-dynamic";

async function loadRules(): Promise<EventAlertRule[]> {
  const stored = await getConfigJSON<{ rules?: EventAlertRule[] }>(ALERT_RULES_KEY, { rules: [] });
  return Array.isArray(stored.rules) ? stored.rules : [];
}

// GET /api/investor-eye/alerts?evaluate=1&hours=24
// Returns the saved rules, and (when `evaluate=1`) which of them currently match
// events in the window — with the reasons each rule fired.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const rules = await loadRules();
  if (searchParams.get("evaluate") !== "1") {
    return NextResponse.json({ rules, presets: true });
  }

  const hoursRaw = Number(searchParams.get("hours") ?? "24");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 24;

  try {
    const state = await assembleState({ hours });
    const evaluation = evaluateRules(state.events, rules);
    // Only include the events that actually matched, so the client does not
    // re-send the whole world state to render the alert list.
    const byId = new Map(state.events.map((e) => [e.id ?? e.dedupKey, e]));
    const matchedEvents = evaluation.matches
      .map((m) => byId.get(m.eventId))
      .filter((e): e is NonNullable<typeof e> => Boolean(e));
    return NextResponse.json({ rules, evaluation, events: matchedEvents, hours });
  } catch (err) {
    console.error("[api/investor-eye/alerts] evaluate error:", err);
    return NextResponse.json({ rules, evaluation: null, error: "Evaluation unavailable." });
  }
}

// POST /api/investor-eye/alerts — create or update one rule (by id).
// Body: { rule: <draft> }  |  { preset: '<preset id>' }
export async function POST(request: Request) {
  const blocked = guardMutation(request, "investor-eye-alerts");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const parsed = parseRule(body.rule ?? body);
    if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

    const rules = await loadRules();
    const idx = rules.findIndex((r) => r.id === parsed.rule.id);
    if (idx >= 0) {
      rules[idx] = { ...rules[idx], ...parsed.rule, createdAt: rules[idx].createdAt };
    } else {
      if (rules.length >= MAX_RULES) {
        return NextResponse.json({ error: `At most ${MAX_RULES} rules.` }, { status: 400 });
      }
      rules.push(parsed.rule);
    }
    await setConfigJSON(ALERT_RULES_KEY, { rules });
    return NextResponse.json({ rules });
  } catch (err) {
    console.error("[api/investor-eye/alerts] POST error:", err);
    return NextResponse.json({ error: "Could not save the rule." }, { status: 500 });
  }
}

// DELETE /api/investor-eye/alerts?id=<ruleId>
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "investor-eye-alerts");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const id = new URL(request.url).searchParams.get("id");
    if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });
    const rules = (await loadRules()).filter((r) => r.id !== id);
    await setConfigJSON(ALERT_RULES_KEY, { rules });
    return NextResponse.json({ rules });
  } catch (err) {
    console.error("[api/investor-eye/alerts] DELETE error:", err);
    return NextResponse.json({ error: "Could not delete the rule." }, { status: 500 });
  }
}

