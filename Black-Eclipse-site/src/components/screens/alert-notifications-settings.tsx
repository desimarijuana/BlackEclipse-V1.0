"use client";

// Alerts / Notifications settings panel — configure the real notification
// channels (Telegram / Discord / ntfy push / Email / generic Webhook).
// Status is honest: "connected" only when required creds are actually set.

import { useEffect, useState } from "react";
import {
  Bell, Save, Check, Monitor, Volume2, DiscordLogo, TelegramLogo, Mail, Rss, Webhook, Newspaper,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { Toggle } from "./settings-ui";
import { useSoundStore } from "@/lib/sounds";
import type { NewsAlertPolicy } from "@/lib/news/alert-policy";
import {
  isSupported,
  secureContext,
  isEnabled as browserNotifyEnabled,
  permission as browserNotifyPermission,
  setEnabled as setBrowserNotifyEnabled,
  type NotificationPermissionState,
} from "@/lib/alerts/browser-notifier";

interface ChannelPatch {
  enabled?: boolean;
  telegramBotToken?: string;
  telegramChatId?: string;
  discordWebhookUrl?: string;
  ntfyTopic?: string;
  ntfyServer?: string;
  emailTo?: string;
  smtpHost?: string;
  smtpPort?: number;
  smtpUser?: string;
  smtpPass?: string;
  webhookUrl?: string;
}

interface StatusRow {
  id: string;
  enabled: boolean;
  configured: boolean;
}

const CHANNEL_FIELDS: Record<string, Array<{ key: keyof ChannelPatch; label: string; placeholder: string; secret?: boolean }>> = {
  telegram: [
    { key: "telegramBotToken", label: "Bot token", placeholder: "123456:ABC-DEF...", secret: true },
    { key: "telegramChatId", label: "Chat ID", placeholder: "your chat / channel id" },
  ],
  discord: [
    { key: "discordWebhookUrl", label: "Webhook URL", placeholder: "https://discord.com/api/webhooks/...", secret: true },
  ],
  ntfy: [
    { key: "ntfyTopic", label: "Topic", placeholder: "my-secret-topic (subscribe in the ntfy phone app)" },
    { key: "ntfyServer", label: "Server (optional)", placeholder: "https://ntfy.sh" },
  ],
  email: [
    { key: "smtpHost", label: "SMTP host", placeholder: "smtp.gmail.com" },
    { key: "smtpPort", label: "SMTP port", placeholder: "587" },
    { key: "smtpUser", label: "SMTP user", placeholder: "you@gmail.com" },
    { key: "smtpPass", label: "SMTP password / app password", placeholder: "app password", secret: true },
    { key: "emailTo", label: "Send to", placeholder: "you@gmail.com" },
  ],
  webhook: [
    { key: "webhookUrl", label: "Webhook URL", placeholder: "https://your-app.example.com/hook", secret: true },
  ],
};

const CHANNEL_DESCRIPTIONS: Record<string, string> = {
  telegram: "Native push on your phone via a Telegram bot.",
  discord: "Post alerts to a Discord channel webhook.",
  ntfy: "Push straight to the ntfy mobile app — no account needed.",
  email: "Email via your own SMTP server (requires nodemailer).",
  webhook: "POST to any endpoint — Slack, Pushover, Home Assistant, your own app.",
};

/** Brand icon + accent tint per delivery channel. */
const CHANNEL_META: Record<string, { icon: React.ElementType; accent: string; tint: string }> = {
  telegram: { icon: TelegramLogo, accent: "text-sky-400", tint: "border-sky-400/20 bg-sky-400/10" },
  discord: { icon: DiscordLogo, accent: "text-indigo-400", tint: "border-indigo-400/20 bg-indigo-400/10" },
  ntfy: { icon: Rss, accent: "text-teal-400", tint: "border-teal-400/20 bg-teal-400/10" },
  email: { icon: Mail, accent: "text-amber-400", tint: "border-amber-400/20 bg-amber-400/10" },
  webhook: { icon: Webhook, accent: "text-violet-400", tint: "border-violet-400/20 bg-violet-400/10" },
};

export function AlertNotificationsPanel() {
  const [channels, setChannels] = useState<Record<string, ChannelPatch>>({});
  const [inApp, setInApp] = useState(true);
  const [status, setStatus] = useState<StatusRow[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Notification sound choices — the SAME per-cue prefs as Settings › Sound
  // (Notifications & alarms), surfaced here so the decision sits next to the
  // channels it applies to.
  const cues = useSoundStore((s) => s.prefs.cues);
  const setCueMuted = useSoundStore((s) => s.setCueMuted);
  const taskdoneOn = !(cues.taskdone?.muted ?? false);
  const notificationOn = !(cues.notification?.muted ?? false);
  const aiResultOn = !(cues.message?.muted ?? false);

  // High-impact news subscription. The server's post-ingest scan
  // (`lib/news/alert-scan.ts`) scores fresh stories and pushes the strongest
  // through the same channels as price alerts; this panel edits its policy.
  const [newsAlerts, setNewsAlerts] = useState<NewsAlertPolicy>({
    enabled: false,
    minScore: 75,
    lookbackMinutes: 180,
    maxPerCycle: 3,
    categories: [],
    tickers: [],
    quietHours: { enabled: false, startHour: 22, endHour: 7 },
  });
  const [newsCategories, setNewsCategories] = useState("");
  const [newsTickers, setNewsTickers] = useState("");
  const [newsMessage, setNewsMessage] = useState<string | null>(null);
  const [savingNews, setSavingNews] = useState(false);

  const NEWS_CATEGORIES = [
    "CENTRAL BANKS", "INFLATION", "JOBS", "ECONOMIC", "GEOPOLITICS",
    "WAR", "TRADE", "REGULATORY", "ENERGY", "MARKETS",
  ] as const;

  // Desktop (OS) notifications — client-only, so probe after mount to keep SSR
  // stable. `supported` gates the whole control; `permission` drives the honest
  // status line (blocked / needs permission / on).
  const [browserSupported, setBrowserSupported] = useState(false);
  const [browserSecure, setBrowserSecure] = useState(true);
  const [browserOn, setBrowserOn] = useState(false);
  const [browserPermission, setBrowserPermission] = useState<NotificationPermissionState>("unsupported");

  useEffect(() => {
    setBrowserSupported(isSupported());
    setBrowserSecure(secureContext());
    setBrowserOn(browserNotifyEnabled());
    setBrowserPermission(browserNotifyPermission());
  }, []);

  const toggleBrowserNotify = async () => {
    const next = !browserOn;
    const result = await setBrowserNotifyEnabled(next);
    setBrowserOn(result.enabled);
    setBrowserPermission(result.permission);
    if (next && !result.effective) {
      setMessage("Desktop notifications need browser permission — allow them in your browser's site settings.");
    } else {
      setMessage(null);
    }
  };

  const testBrowserNotify = () => {
    // Raise the SAME pair a real fired alert uses, through the ONE provider that
    // owns delivery: an always-on in-app toast, plus the desktop notification
    // when enabled+granted. Firing `showAlertNotification` here as well would
    // double the OS notification, so the event is the single trigger.
    window.dispatchEvent(
      new CustomEvent('be:alert-notify', {
        detail: {
          title: 'Desk-test alert',
          body: 'This is a test alert — in-app + desktop delivery are wired.',
          test: true,
        },
      }),
    );
    setMessage(
      browserOn && browserPermission === 'granted'
        ? 'Test sent — check your desktop and the bottom-right toast.'
        : 'In-app toast sent. Desktop notification is off or blocked — enable it and allow browser permission for OS alerts.',
    );
  };

  const load = async () => {
    try {
      const res = await fetch("/api/alerts/channels", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setChannels(data.channels || {});
      setInApp(data.inApp !== false);
      setStatus(data.status || []);
    } catch {}
  };

  const loadNewsAlerts = async () => {
    try {
      const res = await fetch("/api/news/alerts/policy", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const p: Partial<NewsAlertPolicy> = data.policy || {};
      setNewsAlerts((prev) => ({ ...prev, ...p, quietHours: { ...prev.quietHours, ...p.quietHours } }));
      setNewsCategories((p.categories || []).join(", "));
      setNewsTickers((p.tickers || []).join(", "));
    } catch {}
  };

  useEffect(() => {
    load();
    loadNewsAlerts();
  }, []);

  const patch = (id: string, p: ChannelPatch) => {
    setChannels((c) => ({ ...c, [id]: { ...c[id], ...p } }));
  };

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/alerts/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inApp, channels }),
      });
      const data = await res.json();
      setMessage(res.ok ? "Notification channels saved." : data.error || "Failed to save.");
      if (res.ok) load();
    } catch {
      setMessage("Failed to save.");
    } finally {
      setSaving(false);
    }
  };

  const saveNews = async () => {
    setSavingNews(true);
    setNewsMessage(null);
    try {
      const res = await fetch("/api/news/alerts/policy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...newsAlerts,
          categories: newsCategories.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean),
          tickers: newsTickers.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        const p: Partial<NewsAlertPolicy> = data.policy || {};
        setNewsAlerts((prev) => ({ ...prev, ...p, quietHours: { ...prev.quietHours, ...p.quietHours } }));
        setNewsMessage(
          newsAlerts.enabled
            ? "News alerts saved — new high-impact stories will arrive through the channels above."
            : "News alerts saved. Turn the switch on to start watching.",
        );
      } else {
        setNewsMessage(data.error || "Failed to save news alerts.");
      }
    } catch {
      setNewsMessage("Failed to save news alerts.");
    } finally {
      setSavingNews(false);
    }
  };

  const statusFor = (id: string) => status.find((s) => s.id === id);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6">
        <p className="text-[10px] uppercase tracking-[0.2em] text-primary font-bold mb-2 flex items-center gap-1.5">
          <Bell size={11} /> Delivery
        </p>
        <h2 className="font-serif text-xl font-semibold text-foreground">Alerts / Notifications</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Where fired price alerts get delivered. A channel shows <span className="text-emerald-400">connected</span> only
          when its credentials are actually configured.
        </p>
      </div>

      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card p-5 md:p-6 space-y-4">
        <label className="flex items-center gap-2 text-xs cursor-pointer">
          <input type="checkbox" checked={inApp} onChange={(e) => setInApp(e.target.checked)} className="accent-[hsl(var(--primary))]" />
          In-app notices (always recorded to history regardless)
        </label>

        <div className="rounded-xl border border-border/30 p-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Monitor size={14} className="text-primary" />
              <span className="text-xs font-semibold uppercase tracking-wide">Desktop notifications</span>
              {browserOn && browserPermission === "granted" ? (
                <span className="text-[9px] font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-1">
                  <Check size={9} /> on
                </span>
              ) : browserPermission === "denied" ? (
                <span className="text-[9px] font-bold text-rose-400 uppercase tracking-widest">blocked</span>
              ) : (
                <span className="text-[9px] text-muted-foreground uppercase tracking-widest">off</span>
              )}
            </div>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={browserOn}
                disabled={!browserSupported}
                onChange={toggleBrowserNotify}
                className="accent-[hsl(var(--primary))]"
              />
              Enable
            </label>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Native OS notifications on this computer (Windows/macOS/Linux) while a BlackEclipse tab is open.
            {!browserSupported && !browserSecure &&
              " This page is not a secure origin — browsers disable notifications over plain http. Run `npm run setup:tls` once, restart, then reopen at https://blackeclipse."}
            {!browserSupported && browserSecure && " Not supported in this browser."}
            {browserSupported && browserPermission === "denied" &&
              " Your browser has blocked notifications — allow them in the site settings (padlock in the address bar)."}
          </p>
          <Button size="sm" variant="outline" onClick={testBrowserNotify} disabled={!browserOn || browserPermission !== "granted"} className="cursor-pointer rounded-xl">
            Send test notification
          </Button>
        </div>

        <div className="rounded-xl border border-border/30 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Volume2 size={14} className="text-primary" />
            <span className="text-xs font-semibold uppercase tracking-wide">Notification sounds</span>
          </div>
          <label className="flex items-start gap-2 text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={aiResultOn}
              onChange={(e) => setCueMuted("message", !e.target.checked)}
              className="mt-0.5 accent-[hsl(var(--primary))]"
            />
            <span>
              AI result — a sound when an Eclipse reply or AI run finishes.
              <span className="block text-[10px] text-muted-foreground mt-0.5">
                On by default; this switch is the opt-out. It plays even while UI Sounds are off.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2 text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={notificationOn}
              onChange={(e) => setCueMuted("notification", !e.target.checked)}
              className="mt-0.5 accent-[hsl(var(--primary))]"
            />
            <span>Alert cue — a price or news alert fired, an approval is waiting, or a run failed.</span>
          </label>
          <label className="flex items-start gap-2 text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={taskdoneOn}
              onChange={(e) => setCueMuted("taskdone", !e.target.checked)}
              className="mt-0.5 accent-[hsl(var(--primary))]"
            />
            <span>
              Task-done cue — a background task or automation finished.
              <span className="block text-[10px] text-muted-foreground mt-0.5">
                Played independently of UI Sounds; this switch is the opt-out.
              </span>
            </span>
          </label>
          <p className="text-[10px] text-muted-foreground">
            Volume, test buttons, voice packs and custom clips live in Settings › Sound › Notifications &amp; alarms.
          </p>
        </div>

        <div className="rounded-xl border border-border/30 p-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Newspaper size={14} className="text-primary" />
              <span className="text-xs font-semibold uppercase tracking-wide">High-impact news alerts</span>
              {newsAlerts.enabled && (
                <span className="text-[9px] font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-1">
                  <Check size={9} /> on
                </span>
              )}
            </div>
            <Toggle
              checked={newsAlerts.enabled}
              onChange={(v) => setNewsAlerts((s) => ({ ...s, enabled: v }))}
            />
          </div>
          <p className="text-[10px] text-muted-foreground">
            Scores fresh headlines deterministically (tier, corroboration, recency, category, relevance) and pushes
            only high/critical stories through the channels above. The News tab&apos;s High Alert band also surfaces
            upcoming high-impact economic releases. Turning it on starts from now — old headlines are never replayed.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Minimum score</span>
            {[
              { score: 75, label: "Critical only (75+)" },
              { score: 65, label: "High (65+)" },
              { score: 55, label: "High (55+)" },
            ].map((t) => (
              <button
                key={t.score}
                type="button"
                disabled={!newsAlerts.enabled}
                aria-pressed={newsAlerts.minScore === t.score}
                onClick={() => setNewsAlerts((s) => ({ ...s, minScore: t.score }))}
                className={cn(
                  "rounded-full border px-3 py-1 text-[11px] font-semibold cursor-pointer transition-all disabled:opacity-40",
                  newsAlerts.minScore === t.score
                    ? "bg-primary/15 border-primary/50 text-primary"
                    : "border-border/40 text-muted-foreground hover:border-primary/30",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Look back</span>
            {[60, 180, 360, 720].map((m) => (
              <button
                key={m}
                type="button"
                disabled={!newsAlerts.enabled}
                aria-pressed={newsAlerts.lookbackMinutes === m}
                onClick={() => setNewsAlerts((s) => ({ ...s, lookbackMinutes: m }))}
                className={cn(
                  "rounded-full border px-3 py-1 text-[11px] font-semibold cursor-pointer transition-all disabled:opacity-40",
                  newsAlerts.lookbackMinutes === m
                    ? "bg-primary/15 border-primary/50 text-primary"
                    : "border-border/40 text-muted-foreground hover:border-primary/30",
                )}
              >
                {m < 60 ? `${m}m` : `${m / 60}h`}
              </button>
            ))}
            <span className="mx-1 w-px self-stretch bg-border/50" aria-hidden />
            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Max / cycle</span>
            {[1, 3, 5, 10].map((n) => (
              <button
                key={n}
                type="button"
                disabled={!newsAlerts.enabled}
                aria-pressed={newsAlerts.maxPerCycle === n}
                onClick={() => setNewsAlerts((s) => ({ ...s, maxPerCycle: n }))}
                className={cn(
                  "rounded-full border px-3 py-1 text-[11px] font-semibold cursor-pointer transition-all disabled:opacity-40",
                  newsAlerts.maxPerCycle === n
                    ? "bg-primary/15 border-primary/50 text-primary"
                    : "border-border/40 text-muted-foreground hover:border-primary/30",
                )}
              >
                {n}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Categories</span>
            {NEWS_CATEGORIES.map((c) => {
              const on = newsAlerts.categories.includes(c);
              return (
                <button
                  key={c}
                  type="button"
                  disabled={!newsAlerts.enabled}
                  aria-pressed={on}
                  onClick={() =>
                    setNewsAlerts((s) => ({
                      ...s,
                      categories: on ? s.categories.filter((x) => x !== c) : [...s.categories, c],
                    }))
                  }
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[10px] font-semibold cursor-pointer transition-all disabled:opacity-40",
                    on
                      ? "bg-primary/15 border-primary/50 text-primary"
                      : "border-border/40 text-muted-foreground hover:border-primary/30",
                  )}
                >
                  {c}
                </button>
              );
            })}
            {newsAlerts.categories.length > 0 && (
              <button
                type="button"
                disabled={!newsAlerts.enabled}
                onClick={() => setNewsAlerts((s) => ({ ...s, categories: [] }))}
                className="text-[10px] text-muted-foreground underline cursor-pointer disabled:opacity-40"
              >
                any category
              </button>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-[10px] text-muted-foreground">Tickers you follow (optional, comma-separated)</Label>
              <Input
                value={newsTickers}
                disabled={!newsAlerts.enabled}
                onChange={(e) => setNewsTickers(e.target.value)}
                placeholder="AAPL, NVDA, BTC-USD"
                className="text-xs font-mono"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] text-muted-foreground">More categories (optional, comma-separated)</Label>
              <Input
                value={newsCategories}
                disabled={!newsAlerts.enabled}
                onChange={(e) => setNewsCategories(e.target.value)}
                placeholder="TECH, CRYPTO"
                className="text-xs"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={newsAlerts.quietHours.enabled}
                disabled={!newsAlerts.enabled}
                onChange={(e) =>
                  setNewsAlerts((s) => ({ ...s, quietHours: { ...s.quietHours, enabled: e.target.checked } }))
                }
                className="accent-[hsl(var(--primary))]"
              />
              Quiet hours (server-local) —
            </label>
            <Input
              type="number"
              min={0}
              max={23}
              value={newsAlerts.quietHours.startHour}
              disabled={!newsAlerts.enabled || !newsAlerts.quietHours.enabled}
              onChange={(e) =>
                setNewsAlerts((s) => ({ ...s, quietHours: { ...s.quietHours, startHour: Number(e.target.value) } }))
              }
              className="h-8 w-16 text-xs font-mono"
              aria-label="Quiet hours start"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <Input
              type="number"
              min={0}
              max={23}
              value={newsAlerts.quietHours.endHour}
              disabled={!newsAlerts.enabled || !newsAlerts.quietHours.enabled}
              onChange={(e) =>
                setNewsAlerts((s) => ({ ...s, quietHours: { ...s.quietHours, endHour: Number(e.target.value) } }))
              }
              className="h-8 w-16 text-xs font-mono"
              aria-label="Quiet hours end"
            />
            <span className="text-[10px] text-muted-foreground">(24h)</span>
          </div>

          <div className="flex items-center gap-3">
            <Button size="sm" variant="outline" onClick={saveNews} disabled={savingNews} className="cursor-pointer rounded-xl">
              <Save size={13} className="mr-1.5" /> Save news alerts
            </Button>
            {newsMessage && <span className="text-xs text-muted-foreground">{newsMessage}</span>}
          </div>
        </div>

        {Object.entries(CHANNEL_FIELDS).map(([id, fields]) => {
          const st = statusFor(id);
          const cfg = channels[id] || {};
          const meta = CHANNEL_META[id] ?? { icon: Bell, accent: "text-primary", tint: "border-white/10 bg-white/5" };
          const Icon = meta.icon;
          const enabled = cfg?.enabled ?? false;
          const configured = !!st?.configured;
          return (
            <div
              key={id}
              className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3 transition-colors hover:bg-white/[0.04]"
            >
              <div className="flex items-center gap-3">
                <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg border", meta.tint)}>
                  <Icon size={18} className={meta.accent} weight="fill" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold capitalize tracking-wide">{id}</span>
                    {configured ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-emerald-300">
                        <span className="size-1.5 rounded-full bg-emerald-400" /> connected
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                        not configured
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">{CHANNEL_DESCRIPTIONS[id]}</p>
                </div>
                <Toggle checked={enabled} onChange={(v) => patch(id, { enabled: v })} />
              </div>
              {enabled && (
                <div className="grid gap-3 pt-1 sm:grid-cols-2">
                  {fields.map((f) => (
                    <div key={String(f.key)} className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">{f.label}</Label>
                      <Input
                        type={f.secret ? "password" : f.key === "smtpPort" ? "number" : "text"}
                        value={(cfg?.[f.key] as string | number | undefined) ?? ""}
                        placeholder={f.placeholder}
                        onChange={(e) =>
                          patch(id, { [f.key]: f.key === "smtpPort" ? Number(e.target.value) : e.target.value } as ChannelPatch)
                        }
                        className="font-mono text-xs"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        <div className="flex items-center gap-3">
          <Button size="sm" onClick={save} disabled={saving} className="cursor-pointer rounded-xl">
            <Save size={13} className="mr-1.5" /> Save channels
          </Button>
          {message && <span className="text-xs text-muted-foreground">{message}</span>}
        </div>
      </div>
    </div>
  );
}