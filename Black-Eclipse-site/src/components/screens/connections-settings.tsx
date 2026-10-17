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
  Plug, RefreshCcw, Loader2, Trash2, ShieldCheck, AlertCircle, Link2, Copy, Check,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
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
} from "@/lib/harness/channels-browser";

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
  inbound: "poll" | "push";
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
    inbound: "push",
    note: "A Slack app with Event Subscriptions pointing at the webhook URL below; paste the bot token and signing secret.",
    fields: [
      { key: "botToken", label: "Bot token (xoxb-…)", secret: true },
      { key: "signingSecret", label: "Signing secret", secret: true },
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

const SCOPES: Array<{ value: ControlScope; label: string }> = [
  { value: "viewer", label: "Viewer — read-only" },
  { value: "assistant", label: "Assistant — ask the agent" },
  { value: "operator", label: "Operator — mutations (need /confirm)" },
];

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
        icon={Plug}
      />

      {error && (
        <div className="glass-card-subtle flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-amber-300">
          <AlertCircle className="size-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {health && (
        <div className="glass-card-subtle rounded-lg px-3 py-2 text-xs text-muted-foreground">
          Gateway {health.enabled ? "enabled" : "disabled"} · pollers:{" "}
          {health.activePollers.length ? health.activePollers.join(", ") : "none"} ·{" "}
          {health.bindings} binding{health.bindings === 1 ? "" : "s"} · model {health.model.provider}/{health.model.model}
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={() => void load()} disabled={busy}>
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
            <ul className="space-y-1.5">
              {messages.map((m) => (
                <li key={m.id} className="flex items-start gap-2 text-xs">
                  <span
                    className={
                      "mt-0.5 rounded px-1.5 py-0.5 font-mono uppercase " +
                      (m.direction === "in" ? "bg-sky-500/15 text-sky-300" : "bg-emerald-500/15 text-emerald-300")
                    }
                  >
                    {m.direction}
                  </span>
                  <span className="flex-1 truncate text-muted-foreground" title={m.text}>
                    {m.text}
                  </span>
                  <span className="text-muted-foreground/70">{m.kind}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </SubSection>
    </div>
  );
}

function WebhookUrl({ kind }: { kind: ChannelKind }) {
  const [copied, setCopied] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const url = `${origin}/api/channels/webhook/${kind}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be unavailable */
    }
  };
  return (
    <div className="flex items-center gap-2 rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-xs">
      <span className="flex-1 truncate text-muted-foreground">{url}</span>
      <Button variant="ghost" size="sm" onClick={() => void copy()}>
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
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

  return (
    <Panel>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="font-medium">{entry.label}</span>
          {config?.configured ? (
            <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] uppercase text-emerald-300">configured</span>
          ) : (
            <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">not configured</span>
          )}
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
            {entry.inbound === "push" ? "webhook" : "poll"}
          </span>
        </div>
        {config?.configured && (
          <Button variant="ghost" size="sm" onClick={() => void disable()} disabled={busy}>
            <Trash2 className="size-4" />
            <span className="ml-1">Disable</span>
          </Button>
        )}
      </div>

      <p className="mt-1 text-xs text-muted-foreground">{entry.note}</p>

      {entry.inbound === "push" && (
        <div className="mt-3">
          <p className="mb-1 text-xs text-muted-foreground">Inbound webhook URL</p>
          <WebhookUrl kind={entry.kind} />
        </div>
      )}

      {config?.configured && (
        <div className="mt-3 text-xs text-muted-foreground">
          Keys already set:{" "}
          {entry.fields.filter((f) => f.key in (config.config ?? {})).map((f) => f.label).join(", ") || "—"}
          {" · "}
          <span className={config.secretsEncrypted ? "text-emerald-300/80" : "text-amber-300/80"}>
            {config.secretsEncrypted ? "encrypted at rest" : "stored unencrypted (vault unavailable)"}
          </span>
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
              className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm outline-none focus:border-white/25"
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

      {config?.configured && (
        <div className="mt-3 flex items-end gap-2">
          <label className="flex-1 text-xs">
            <span className="mb-1 block text-muted-foreground">Link code scope</span>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as ControlScope)}
              className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm outline-none focus:border-white/25"
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
      )}

      {linkCode && (
        <div className="glass-card-subtle mt-3 rounded-md px-3 py-2 text-sm">
          <div className="flex items-center gap-2">
            <Link2 className="size-4 text-sky-300" />
            <span>
              Send <code className="rounded bg-black/40 px-1">{`/link ${linkCode.code}`}</code> from the account.
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Expires {new Date(linkCode.expiresAt).toLocaleTimeString()} · grants the <strong>{linkCode.scope}</strong> scope.
          </p>
        </div>
      )}

      {bindings.length > 0 && (
        <div className="mt-3 space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Linked accounts</p>
          {bindings.map((b) => (
            <BindingRow key={b.id} binding={b} onChanged={onChanged} />
          ))}
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
    <div className="flex items-center gap-2 text-xs">
      <span className="flex-1 truncate">
        {binding.displayName || binding.externalId}
        <span className="ml-1 text-muted-foreground/70">#{binding.externalId}</span>
      </span>
      <select
        value={binding.scope}
        onChange={(e) => void changeScope(e.target.value as ControlScope)}
        disabled={busy}
        className="rounded border border-white/10 bg-black/30 px-1.5 py-1 outline-none"
      >
        {SCOPES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.value}
          </option>
        ))}
      </select>
      <Button variant="ghost" size="sm" onClick={() => void revoke()} disabled={busy}>
        <Trash2 className="size-3.5" />
      </Button>
    </div>
  );
}
