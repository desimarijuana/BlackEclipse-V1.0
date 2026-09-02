// Notification channels config (Telegram/Discord/ntfy/Email/Webhook) for the
// Alerts settings section. Read endpoints report honest configured status.
import {
  getAlertChannels,
  setAlertChannels,
  channelsStatus,
  type AlertChannels,
} from "@/lib/alerts/notifier";
import { checkMutationAllowed } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// GET /api/alerts/channels — masked config + honest per-channel status.
export async function GET() {
  try {
    const cfg = await getAlertChannels();
    const status = await channelsStatus();
    return Response.json({ channels: cfg.channels, inApp: cfg.inApp, status });
  } catch (err) {
    console.error("[api/alerts/channels] GET error:", err);
    return Response.json({ error: "failed" }, { status: 500 });
  }
}

// POST /api/alerts/channels — save channel config. Secrets are write-only.
export async function POST(request: Request) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) return Response.json({ error: guard.reason }, { status: 403 });
  try {
    const body = (await request.json()) as Partial<AlertChannels> & { inApp?: boolean };
    const current = await getAlertChannels();
    const next: AlertChannels = {
      inApp: body.inApp !== false,
      channels: { ...current.channels },
    };
    for (const [id, patch] of Object.entries(body.channels || {})) {
      next.channels[id as keyof AlertChannels["channels"]] = {
        ...current.channels[id as keyof AlertChannels["channels"]],
        ...patch,
      } as never;
    }
    await setAlertChannels(next);
    const status = await channelsStatus();
    return Response.json({ ok: true, status });
  } catch (err) {
    console.error("[api/alerts/channels] POST error:", err);
    return Response.json({ error: "failed to save" }, { status: 500 });
  }
}
