"use client";

// Alerts / Notifications settings panel — configure the real notification
// channels (Telegram / Discord / ntfy push / Email / generic Webhook).
// Status is honest: "connected" only when required creds are actually set.

import { useEffect, useState } from "react";
import { Bell, Save, Check, Monitor, Volume2 } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSoundStore } from "@/lib/sounds";
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

  useEffect(() => {
    load();
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
              checked={taskdoneOn}
              onChange={(e) => setCueMuted("taskdone", !e.target.checked)}
              className="mt-0.5 accent-[hsl(var(--primary))]"
            />
            <span>
              Task-done alarm — a loud sound when a background task, agent run or bot run finishes.
              <span className="block text-[10px] text-muted-foreground mt-0.5">
                It plays even while UI Sounds are off; this switch is the opt-out.
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
            <span>System &amp; approval cue — an approval is waiting for you or a run failed.</span>
          </label>
          <p className="text-[10px] text-muted-foreground">
            Volume, test buttons, voice packs and custom clips live in Settings › Sound › Notifications &amp; alarms.
          </p>
        </div>

        {Object.entries(CHANNEL_FIELDS).map(([id, fields]) => {
          const st = statusFor(id);
          const cfg = channels[id] || {};
          return (
            <div key={id} className="rounded-xl border border-border/30 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={cfg?.enabled ?? false}
                    onChange={(e) => patch(id, { enabled: e.target.checked })}
                    className="accent-[hsl(var(--primary))]"
                  />
                  <span className="text-xs font-semibold uppercase tracking-wide">{id}</span>
                  {st?.configured ? (
                    <span className="text-[9px] font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-1">
                      <Check size={9} /> connected
                    </span>
                  ) : (
                    <span className="text-[9px] text-muted-foreground uppercase tracking-widest">not configured</span>
                  )}
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground">{CHANNEL_DESCRIPTIONS[id]}</p>
              {(cfg?.enabled ?? false) && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {fields.map((f) => (
                    <div key={String(f.key)} className="space-y-1">
                      <Label className="text-[10px]">{f.label}</Label>
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