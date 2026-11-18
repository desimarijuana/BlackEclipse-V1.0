"use client";

// ── Connections settings panel ───────────────────────────────────────────────
// The operator surface for the Channel Gateway. It is a UI for the runtime's
// binding/scope state, never the authority itself: channel enable/config POST to
// `/api/channels/*`, which the Python runtime enforces. A credential is written
// once and never returned — the API answers with presence flags only.
//
// Pull channels (Telegram/Discord/Email) connect outward, so no public URL is
// needed. Push channels (Slack/WhatsApp/Webhook) expose a public webhook URL that
// the provider posts to; the runtime verifies the provider's HMAC signature.

import { useCallback, useEffect, useState } from "react";
import {
  Activity, AlertCircle, Check, ChatsCircle, Copy, DiscordLogo, GoogleLogo, Link2, Loader2, Mail,
  MicrosoftTeamsLogo, RefreshCcw, ShieldCheck, SlackLogo, TelegramLogo, Trash2, Webhook, WhatsappLogo,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { copyText } from "@/lib/desktop/clipboard";
import { Panel, SectionHeader, SubSection } from "./settings-ui";
import {
  channelsHealth,
  configureChannel,
  createLinkCode,
  deleteChannel,
  listBindings,
  listChannels,
  listChannelMessages,
  revokeBinding,
  setBindingScope,
  type ChannelBindingView,
  type ChannelConfigView,
  type ChannelKind,
  type ChannelLinkCode,
  type ChannelMessageView,
  type ChannelsHealth,
  type ControlScope,
} from "@/lib/harness/clients/channels-browser";

interface FieldSpec {
  key: string;
  label: string;
  secret?: boolean;
  number?: boolean;
  placeholder?: string;
}

interface KindSpec {
  kind: ChannelKind;
  label: string;
  inbound: "poll" | "push" | "both";
  note: string;
  fields: FieldSpec[];
}

const KINDS: KindSpec[] = [
  {
    kind: "telegram",
    label: "Telegram",
    inbound: "poll",
    note: "Create a bot with @BotFather and paste its token. Long-poll — no public URL needed.",
    fields: [{ key: "botToken", label: "Bot token", secret: true, placeholder: "123456:ABC-DEF…" }],
  },
  {
    kind: "discord",
    label: "Discord",
    inbound: "poll",
    note: "Create a bot in the Developer Portal, enable the Message Content intent, and paste its token. Gateway WebSocket — no public URL needed.",
    fields: [{ key: "botToken", label: "Bot token", secret: true }],
  },
  {
    kind: "email",
    label: "Email",
    inbound: "poll",
    note: "IMAP inbox for commands, SMTP for replies. Poll-based — no public URL needed.",
    fields: [
      { key: "imapHost", label: "IMAP host", placeholder: "imap.gmail.com" },
      { key: "imapPort", label: "IMAP port", number: true, placeholder: "993" },
      { key: "imapUser", label: "IMAP user" },
      { key: "imapPass", label: "IMAP password", secret: true },
      { key: "smtpHost", label: "SMTP host", placeholder: "smtp.gmail.com" },
      { key: "smtpPort", label: "SMTP port", number: true, placeholder: "587" },
      { key: "smtpUser", label: "SMTP user" },
      { key: "smtpPass", label: "SMTP password", secret: true },
      { key: "fromAddress", label: "From address", placeholder: "you@example.com" },
    ],
  },
  {
    kind: "slack",
    label: "Slack",
    inbound: "both",
    note: "Socket Mode needs a bot token + app-level token and no public URL. For the Events webhook path, add the signing secret and point Event Subscriptions at the webhook URL below.",
    fields: [
      { key: "botToken", label: "Bot token (xoxb-…)", secret: true },
      { key: "appToken", label: "App-level token (xapp-…)", secret: true },
      { key: "signingSecret", label: "Signing secret", secret: true },
      { key: "defaultChannel", label: "Default channel ID" },
    ],
  },
  {
    kind: "whatsapp",
    label: "WhatsApp",
    inbound: "push",
    note: "Meta WhatsApp Cloud API. Set the webhook URL + verify token in the Meta app; paste the access token, phone number id and app secret.",
    fields: [
      { key: "accessToken", label: "Access token", secret: true },
      { key: "phoneNumberId", label: "Phone number id" },
      { key: "appSecret", label: "App secret", secret: true },
      { key: "verifyToken", label: "Verify token", secret: true },
    ],
  },
  {
    kind: "teams",
    label: "Microsoft Teams",
    inbound: "push",
    note: "Register an Azure Bot, paste the app id + password, and point the Bot Framework messaging endpoint at the webhook URL below.",
    fields: [
      { key: "appId", label: "Bot app ID" },
      { key: "appPassword", label: "Bot app password", secret: true },
      { key: "tenantId", label: "Tenant ID (common = multi-tenant)" },
      { key: "defaultConversationId", label: "Default conversation ID" },
      { key: "defaultServiceUrl", label: "Default service URL" },
    ],
  },
  {
    kind: "google_chat",
    label: "Google Chat",
    inbound: "push",
    note: "A Chat app with HTTP endpoint delivery. Paste service-account JSON (or enable ADC) and the project number used as the JWT audience.",
    fields: [
      { key: "credentialsJson", label: "Service-account JSON / key path", secret: true },
      { key: "useAdc", label: "Use ADC (true/false)" },
      { key: "projectNumber", label: "Project number" },
      { key: "defaultSpaceId", label: "Default space ID (spaces/…)" },
      { key: "pubsubAudience", label: "Pub/Sub audience (optional)" },
    ],
  },
  {
    kind: "lark",
    label: "Lark / Feishu",
    inbound: "both",
    note: "WebSocket mode needs only the app id + secret (install the optional lark-oapi extra) and no public URL. For webhook delivery, subscribe to im.message.receive_v1 and set the verification token / encrypt key.",
    fields: [
      { key: "appId", label: "App ID" },
      { key: "appSecret", label: "App secret", secret: true },
      { key: "defaultChatId", label: "Default chat ID" },
      { key: "verificationToken", label: "Verification token", secret: true },
      { key: "encryptKey", label: "Encrypt key", secret: true },
      { key: "domain", label: "Domain (open.feishu.cn / open.larksuite.com)" },
      { key: "useWebsocket", label: "Use WebSocket (true/false)" },
    ],
  },
  {
    kind: "webhook",
    label: "Webhook",
    inbound: "push",
    note: "A signed generic inbound. The caller signs the raw body with the webhook secret (X-Eclipse-Signature: sha256=<hmac>); replies POST to the reply URL.",
    fields: [
      { key: "replyUrl", label: "Reply URL" },
      { key: "replyToken", label: "Reply bearer token", secret: true },
      { key: "webhookSecret", label: "Inbound webhook secret", secret: true },
    ],
  },
];

/** Per-channel brand icon + accent tint used across the panel. */
const CHANNEL_META: Record<ChannelKind, { icon: React.ElementType; accent: string; tint: string }> = {
  telegram: { icon: TelegramLogo, accent: "text-sky-400", tint: "border-sky-400/20 bg-sky-400/10" },
  discord: { icon: DiscordLogo, accent: "text-indigo-400", tint: "border-indigo-400/20 bg-indigo-400/10" },
  email: { icon: Mail, accent: "text-amber-400", tint: "border-amber-400/20 bg-amber-400/10" },
  slack: { icon: SlackLogo, accent: "text-violet-400", tint: "border-violet-400/20 bg-violet-400/10" },
  whatsapp: { icon: WhatsappLogo, accent: "text-emerald-400", tint: "border-emerald-400/20 bg-emerald-400/10" },
  teams: { icon: MicrosoftTeamsLogo, accent: "text-indigo-400", tint: "border-indigo-400/20 bg-indigo-400/10" },
  google_chat: { icon: GoogleLogo, accent: "text-sky-400", tint: "border-sky-400/20 bg-sky-400/10" },
  lark: { icon: ChatsCircle, accent: "text-cyan-400", tint: "border-cyan-400/20 bg-cyan-400/10" },
  webhook: { icon: Webhook, accent: "text-rose-400", tint: "border-rose-400/20 bg-rose-400/10" },
};

const SCOPES: Array<{ value: ControlScope; label: string }> = [
  { value: "viewer", label: "Viewer — read-only" },
  { value: "assistant", label: "Assistant — ask the agent" },
  { value: "operator", label: "Operator — mutations (need /confirm)" },
];

const FIELD_INPUT =
  "w-full rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-2 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/50 focus:border-primary/50 focus:ring-2 focus:ring-primary/20";

export function ConnectionsSettingsPanel() {
  const [health, setHealth] = useState<ChannelsHealth | null>(null);
  const [channels, setChannels] = useState<ChannelConfigView[]>([]);
  const [bindings, setBindings] = useState<ChannelBindingView[]>([]);
  const [messages, setMessages] = useState<ChannelMessageView[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [nextHealth, nextChannels, nextBindings, nextMessages] = await Promise.all([
        channelsHealth(),
        listChannels(),
        listBindings(),
        listChannelMessages({ limit: 25 }),
      ]);
      setHealth(nextHealth);
      setChannels(nextChannels);
      setBindings(nextBindings);
      setMessages(nextMessages);
    } catch (err) {
      setError(err instanceof Error ? err.message : "channel gateway unavailable");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const configFor = (kind: ChannelKind) => channels.find((c) => c.channel === kind);

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Connections"
        description="Connect an external account to Eclipse so you can see and drive the app remotely. Every action is scope-gated and audited; mutating actions ask for an in-channel confirmation."
        icon={ChatsCircle}
      />

      {error && (
        <div className="glass-card-subtle flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm text-amber-300">
          <AlertCircle className="size-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="glass-card-subtle flex flex-wrap items-center gap-x-2.5 gap-y-1.5 rounded-xl px-3.5 py-2.5 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Activity size={13} className={health?.enabled ? "text-emerald-400" : "text-muted-foreground/60"} />
          Gateway {health ? (health.enabled ? "enabled" : "disabled") : "unavailable"}
        </span>
        <span className="text-white/15">·</span>
        <span>
          pollers: {health?.activePollers.length ? health.activePollers.join(", ") : "none"}
        </span>
        <span className="text-white/15">·</span>
        <span>
          {health?.bindings ?? 0} binding{(health?.bindings ?? 0) === 1 ? "" : "s"}
        </span>
        {health && (
          <>
            <span className="text-white/15">·</span>
            <span>
              model {health.model.provider}/{health.model.model}
            </span>
          </>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void load()}
          disabled={busy}
          className="ml-auto -my-1 h-7"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <RefreshCcw className="size-4" />}
          <span className="ml-1">Refresh</span>
        </Button>
      </div>

      <div className="space-y-3">
        {KINDS.map((entry) => (
          <ChannelCard
            key={entry.kind}
            entry={entry}
            config={configFor(entry.kind)}
            bindings={bindings.filter((b) => b.kind === entry.kind && b.status === "active")}
            onChanged={load}
          />
        ))}
      </div>

      <SubSection title="Recent activity" description="The last messages sent and received across every channel.">
        <Panel>
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No channel activity yet.</p>
          ) : (
            <ul className="space-y-2">
              {messages.map((m) => {
                const meta = CHANNEL_META[m.kind];
                const Icon = meta?.icon ?? ChatsCircle;
                return (
                  <li key={m.id} className="flex items-start gap-2.5 text-xs">
                    <span
                      className={cn(
                        "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border",
                        meta?.tint ?? "border-white/10 bg-white/5",
                      )}
                    >
                      <Icon size={12} className={meta?.accent} />
                    </span>
                    <span
                      className={cn(
                        "mt-0.5 rounded px-1.5 py-0.5 font-mono uppercase",
                        m.direction === "in" ? "bg-sky-500/15 text-sky-300" : "bg-emerald-500/15 text-emerald-300",
                      )}
                    >
                      {m.direction}
                    </span>
                    <span className="flex-1 truncate text-muted-foreground" title={m.text}>
                      {m.text}
                    </span>
                    <span className="shrink-0 text-muted-foreground/60">{m.kind}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </SubSection>
    </div>
  );
}

function StatusPill({ configured }: { configured: boolean }) {
  return configured ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-300">
      <span className="size-1.5 rounded-full bg-emerald-400" />
      connected
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      <span className="size-1.5 rounded-full bg-muted-foreground/50" />
      not set
    </span>
  );
}

function WebhookUrl({ kind }: { kind: ChannelKind }) {
  const [copied, setCopied] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const url = `${origin}/api/channels/webhook/${kind}`;
  const copy = async () => {
    if (!(await copyText(url))) return;
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/25 px-2.5 py-1.5 text-xs">
      <span className="flex-1 truncate font-mono text-muted-foreground">{url}</span>
      <Button variant="ghost" size="sm" onClick={() => void copy()} className="h-6 w-6 p-0">
        {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
      </Button>
    </div>
  );
}

function ChannelCard({
  entry,
  config,
  bindings,
  onChanged,
}: {
  entry: KindSpec;
  config?: ChannelConfigView;
  bindings: ChannelBindingView[];
  onChanged: () => Promise<void>;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [scope, setScope] = useState<ControlScope>("assistant");
  const [linkCode, setLinkCode] = useState<ChannelLinkCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const meta = CHANNEL_META[entry.kind];
  const Icon = meta.icon;
  const configured = !!config?.configured;

  const setField = (key: string, value: string) => setDraft((d) => ({ ...d, [key]: value }));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const cfg: Record<string, unknown> = {};
      for (const field of entry.fields) {
        const value = (draft[field.key] ?? "").trim();
        if (value) cfg[field.key] = field.number ? Number(value) : value;
      }
      await configureChannel(entry.kind, true, cfg);
      setDraft({});
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await deleteChannel(entry.kind);
      setLinkCode(null);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "disable failed");
    } finally {
      setBusy(false);
    }
  };

  const mintCode = async () => {
    setBusy(true);
    setError(null);
    try {
      setLinkCode(await createLinkCode(entry.kind, scope));
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not create a link code");
    } finally {
      setBusy(false);
    }
  };

  const setKeys = entry.fields.filter((f) => f.key in (config?.config ?? {}));

  return (
    <Panel className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-xl border",
              meta.tint,
            )}
          >
            <Icon size={20} className={meta.accent} weight="fill" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{entry.label}</span>
              <StatusPill configured={configured} />
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{entry.note}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground sm:inline">
            {entry.inbound === "push" ? "webhook" : entry.inbound === "both" ? "socket + webhook" : "poll"}
          </span>
          {configured && (
            <Button variant="ghost" size="sm" onClick={() => void disable()} disabled={busy}>
              <Trash2 className="size-4" />
              <span className="ml-1 hidden sm:inline">Disable</span>
            </Button>
          )}
        </div>
      </div>

      {configured && (
        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <ShieldCheck size={13} className={config?.secretsEncrypted ? "text-emerald-400" : "text-amber-400"} />
            {config?.secretsEncrypted ? "encrypted at rest" : "stored unencrypted (vault unavailable)"}
          </span>
          {setKeys.length > 0 && (
            <>
              <span className="text-white/15">·</span>
              <span>keys set: {setKeys.map((f) => f.label).join(", ")}</span>
            </>
          )}
        </div>
      )}

      {entry.inbound !== "poll" && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Inbound webhook URL</p>
          <WebhookUrl kind={entry.kind} />
        </div>
      )}

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {entry.fields.map((field) => (
          <label key={field.key} className="text-xs">
            <span className="mb-1 block text-muted-foreground">{field.label}</span>
            <input
              type={field.secret ? "password" : "text"}
              inputMode={field.number ? "numeric" : undefined}
              value={draft[field.key] ?? ""}
              onChange={(e) => setField(field.key, e.target.value)}
              placeholder={field.placeholder ?? (field.secret ? "••••••" : "")}
              className={FIELD_INPUT}
            />
          </label>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-end gap-2">
        <Button variant="default" size="sm" onClick={() => void save()} disabled={busy}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
          <span className="ml-1">Save</span>
        </Button>
      </div>

      {configured && (
        <div className="mt-4 border-t border-white/[0.06] pt-4">
          <div className="flex flex-wrap items-end gap-2">
            <label className="min-w-[180px] flex-1 text-xs">
              <span className="mb-1 block text-muted-foreground">Link code scope</span>
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value as ControlScope)}
                className={cn(FIELD_INPUT, "appearance-none pr-8")}
              >
                {SCOPES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <Button variant="default" size="sm" onClick={() => void mintCode()} disabled={busy}>
              <Link2 className="size-4" />
              <span className="ml-1">Generate link code</span>
            </Button>
          </div>

          {linkCode && (
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-sky-400/20 bg-sky-400/10 px-3 py-2 text-xs">
              <Link2 className="size-4 shrink-0 text-sky-300" />
              <span>
                Send{" "}
                <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-sky-200">{`/link ${linkCode.code}`}</code>{" "}
                from the account.
              </span>
              <span className="w-full text-[10px] text-muted-foreground sm:ml-auto sm:w-auto">
                expires {new Date(linkCode.expiresAt).toLocaleTimeString()} · grants{" "}
                <strong className="text-foreground/80">{linkCode.scope}</strong>
              </span>
            </div>
          )}

          {bindings.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Linked accounts</p>
              {bindings.map((b) => (
                <BindingRow key={b.id} binding={b} onChanged={onChanged} />
              ))}
            </div>
          )}
        </div>
      )}

      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
    </Panel>
  );
}

function BindingRow({ binding, onChanged }: { binding: ChannelBindingView; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);

  const changeScope = async (scope: ControlScope) => {
    setBusy(true);
    try {
      await setBindingScope(binding.id, scope);
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    setBusy(true);
    try {
      await revokeBinding(binding.id);
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-xs">
      <span className="flex-1 truncate">
        {binding.displayName || binding.externalId}
        <span className="ml-1 text-muted-foreground/60">#{binding.externalId}</span>
      </span>
      <select
        value={binding.scope}
        onChange={(e) => void changeScope(e.target.value as ControlScope)}
        disabled={busy}
        className="rounded-md border border-white/10 bg-black/30 px-1.5 py-1 text-xs outline-none focus:border-primary/50"
      >
        {SCOPES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.value}
          </option>
        ))}
      </select>
      <Button variant="ghost" size="sm" onClick={() => void revoke()} disabled={busy} className="h-6 w-6 p-0">
        <Trash2 className="size-3.5" />
      </Button>
    </div>
  );
}
