// Alert dispatch — sends fired alerts through configured channels
// (Telegram / Discord / ntfy push / Email / generic webhook), records a
// PriceAlertEvent for history, and powers the in-app notice stream.
//
// Channel config lives in SystemConfig under "alert_channels" (settings UI).
// Status is honest: a channel is "configured" only when its required
// credential fields are actually present. If nothing is configured, the event
// is still recorded and surfaced in-app.

import { prisma } from "@/lib/db";
import { getConfigJSON, setConfigJSON } from "@/lib/settings";
import { describeFire, type ConditionDetail } from "./conditionEvaluator";

export type ChannelId = "telegram" | "discord" | "ntfy" | "email" | "webhook";

export interface ChannelConfig {
  enabled: boolean;
  // telegram
  telegramBotToken?: string;
  telegramChatId?: string;
  // discord
  discordWebhookUrl?: string;
  // ntfy (push-to-phone, zero-account)
  ntfyTopic?: string;
  ntfyServer?: string; // default https://ntfy.sh
  // email (SMTP)
  emailTo?: string;
  smtpHost?: string;
  smtpPort?: number;
  smtpUser?: string;
  smtpPass?: string;
  // generic webhook
  webhookUrl?: string;
}

export interface AlertChannels {
  inApp: boolean;
  channels: Partial<Record<ChannelId, ChannelConfig>>;
}

export const DEFAULT_CHANNELS: AlertChannels = {
  inApp: true,
  channels: {},
};

const CHANNELS_KEY = "alert_channels";

export async function getAlertChannels(): Promise<AlertChannels> {
  const cfg = await getConfigJSON<AlertChannels>(CHANNELS_KEY, DEFAULT_CHANNELS);
  return { inApp: cfg.inApp !== false, channels: cfg.channels || {} };
}

export async function setAlertChannels(next: AlertChannels): Promise<AlertChannels> {
  await setConfigJSON(CHANNELS_KEY, next);
  return next;
}

/** Honest per-channel configured check — never claims configured without creds. */
export function channelConfigured(id: ChannelId, c?: ChannelConfig): boolean {
  if (!c?.enabled) return false;
  switch (id) {
    case "telegram":
      return Boolean(c.telegramBotToken && c.telegramChatId);
    case "discord":
      return Boolean(c.discordWebhookUrl);
    case "ntfy":
      return Boolean(c.ntfyTopic);
    case "email":
      return Boolean(c.smtpHost && c.emailTo);
    case "webhook":
      return Boolean(c.webhookUrl);
    default:
      return false;
  }
}

export function channelsStatus(): Promise<
  Array<{ id: ChannelId; enabled: boolean; configured: boolean }>
> {
  return getAlertChannels().then((cfg) =>
    (["telegram", "discord", "ntfy", "email", "webhook"] as ChannelId[]).map((id) => ({
      id,
      enabled: cfg.channels[id]?.enabled ?? false,
      configured: channelConfigured(id, cfg.channels[id]),
    }))
  );
}

async function post(url: string, body: unknown, headers?: Record<string, string>) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

async function sendTelegram(c: ChannelConfig, msg: string) {
  await post(
    `https://api.telegram.org/bot${c.telegramBotToken}/sendMessage`,
    { chat_id: c.telegramChatId, text: msg }
  );
}

async function sendDiscord(c: ChannelConfig, msg: string) {
  await post(c.discordWebhookUrl!, { content: msg });
}

async function sendNtfy(c: ChannelConfig, msg: string) {
  const server = (c.ntfyServer || "https://ntfy.sh").replace(/\/$/, "");
  await post(`${server}/${c.ntfyTopic}`, msg, { Title: "Black Eclipse Alert" });
}

async function sendWebhook(c: ChannelConfig, msg: string) {
  await post(c.webhookUrl!, { text: msg, message: msg, symbol: undefined });
}

async function sendEmail(c: ChannelConfig, msg: string) {
  const nodemailer = (await import("nodemailer")).default;
  try {
    const transport = nodemailer.createTransport({
      host: c.smtpHost,
      port: c.smtpPort ?? 587,
      secure: (c.smtpPort ?? 587) === 465,
      auth: c.smtpUser ? { user: c.smtpUser, pass: c.smtpPass } : undefined,
    });
    await transport.sendMail({
      from: c.smtpUser || c.emailTo,
      to: c.emailTo,
      subject: "Black Eclipse Price Alert",
      text: msg,
    });
  } catch {
    throw new Error("email send failed (check SMTP host/port/credentials)");
  }
}
/** In-app notice ring buffer (latest 100) — served to the UI via /api/alerts/live. */
const inAppNotices: Array<{ msg: string; firedAt: string; test?: boolean }> = [];
export function recentNotices() {
  return [...inAppNotices].reverse();
}

export interface JobMessageArgs {
  /** The i18n key the runtime sent — never a composed sentence. */
  templateKey: string;
  /** The parameters the runtime sent (a job name, a count). */
  params: Record<string, string | number>;
  /** The user's chosen destination label, or null. */
  target?: string | null;
}

/**
 * Render a job's delivery message on the app surface.
 *
 * The runtime hands the surface a KEY + params (Phase 11 §6.1); this is the TS
 * half that resolves it. It NEVER accepts a pre-composed sentence, so every word
 * of a delivered message is translatable and visible to the jargon gate. A
 * message that cannot be resolved falls back to a plain, honest line.
 */
export function renderJobMessage(
  args: JobMessageArgs,
  translate: (key: string, vars?: Record<string, string | number>) => string,
): string {
  try {
    const rendered = translate(args.templateKey, args.params);
    // `translate` returns the key itself when it is unknown; treat that as failure.
    if (rendered && rendered !== args.templateKey) return rendered;
  } catch {
    /* fall through to the honest default */
  }
  return translate("jobs.delivery.message.trouble", {
    jobName: String(args.params.jobName ?? ""),
  });
}

export interface DispatchArgs {
  alertId: string;
  alertName: string;
  symbols: string[];
  details: ConditionDetail[];
  test?: boolean;
}

/**
 * Dispatch one fired alert: build the message, send to every enabled AND
 * configured channel, record the PriceAlertEvent, bump the in-app feed.
 */
export async function dispatchAlert(args: DispatchArgs): Promise<{ delivered: string[]; failed: string[] }> {
  const cfg = await getAlertChannels();
  const symbol = args.symbols[0] ?? "TEST";
  const msg = args.test
    ? `TEST — ${args.alertName}: ${describeFire(symbol, args.details)}`
    : describeFire(symbol, args.details);

  const delivered: string[] = [];
  const failed: string[] = [];

  for (const [id, c] of Object.entries(cfg.channels) as Array<[ChannelId, ChannelConfig | undefined]>) {
    if (!channelConfigured(id, c)) continue;
    try {
      if (id === "telegram") await sendTelegram(c!, msg);
      else if (id === "discord") await sendDiscord(c!, msg);
      else if (id === "ntfy") await sendNtfy(c!, msg);
      else if (id === "webhook") await sendWebhook(c!, msg);
      else if (id === "email") await sendEmail(c!, msg);
      delivered.push(id);
    } catch (err) {
      failed.push(`${id}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // Always record history + in-app notice, even with zero channels configured.
  await prisma.priceAlertEvent.create({
    data: {
      alertId: args.alertId,
      symbol,
      detail: msg + (failed.length ? ` [delivery failed: ${failed.join("; ")}]` : ""),
    },
  });
  if (cfg.inApp) {
    inAppNotices.push({ msg, firedAt: new Date().toISOString(), test: args.test });
    if (inAppNotices.length > 100) inAppNotices.shift();
  }

  return { delivered, failed };
}