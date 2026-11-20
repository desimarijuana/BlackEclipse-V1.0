"use client";

// ── Settings › News › display & delivery ────────────────────────────────────
// The News section used to configure only feeds/providers. This panel adds the
// two client-side surfaces an operator actually feels:
//
//   * News cards — the same `be_news_card_settings` the News tab's inline
//     Customize panel edits (layout, density, visible rows, page size, sort,
//     auto-refresh). Changes here apply live: `card-settings` emits a
//     same-document event the News tab listens for.
//   * Pop-ups & notifications — the delivery switches for the root news
//     watcher: background watch, in-app pop-up card, desktop notification, the
//     alert sound, upcoming macro releases, watchlist-only and the minimum
//     importance score. The header ledger entry is always recorded while the
//     watch is on.
//
// Stored per-browser in localStorage (no server round-trip), matching Sound.

import { useEffect, useState } from "react";
import {
  Bell, Check, LayoutGrid, Monitor, Newspaper, RotateCcw, SlidersHorizontal, Volume2,
} from "@/lib/icons";
import { ALERT_NOTIFY_EVENT } from "@/lib/alerts/browser-notifier";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Panel, SubSection, Toggle } from "./settings-ui";
import {
  clearCardSettings,
  DEFAULT_CARD_SETTINGS,
  loadCardSettings,
  saveCardSettings,
  clampPerPage,
  MAX_PER_PAGE,
  type CardSettings,
} from "@/lib/news/card-settings";
import {
  NEWS_NOTIFY_MIN_SCORES,
  readNewsWatchlist,
  useNewsNotificationPrefs,
} from "@/lib/news/notification-prefs";

function Choice({
  active, disabled, onClick, children, title,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={active}
      title={title}
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-[11px] font-semibold transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed",
        active
          ? "bg-primary/15 border-primary/50 text-primary"
          : "border-border/40 text-muted-foreground hover:border-primary/30",
      )}
    >
      {children}
    </button>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function CardToggleRow({
  label, hint, checked, onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border border-border/30 px-3 py-2.5">
      <div className="min-w-0">
        <p className="text-xs font-semibold text-foreground">{label}</p>
        <p className="mt-0.5 text-[10px] text-muted-foreground">{hint}</p>
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

export function NewsSettingsPanel() {
  const [cards, setCards] = useState<CardSettings>(DEFAULT_CARD_SETTINGS);
  const [cardsReady, setCardsReady] = useState(false);
  const [watchlistCount, setWatchlistCount] = useState(0);
  const [tested, setTested] = useState(false);

  const prefs = useNewsNotificationPrefs((s) => s.prefs);
  const hydrate = useNewsNotificationPrefs((s) => s.hydrate);
  const update = useNewsNotificationPrefs((s) => s.update);
  const resetPrefs = useNewsNotificationPrefs((s) => s.reset);

  useEffect(() => {
    setCards(loadCardSettings());
    setWatchlistCount(readNewsWatchlist().length);
    setCardsReady(true);
    hydrate();
  }, [hydrate]);

  const updateCards = (patch: Partial<CardSettings>) => {
    setCards((prev) => {
      const next = { ...prev, ...patch };
      saveCardSettings(next);
      return next;
    });
  };

  const resetCards = () => {
    clearCardSettings();
    setCards(DEFAULT_CARD_SETTINGS);
  };

  const sendTest = () => {
    window.dispatchEvent(
      new CustomEvent(ALERT_NOTIFY_EVENT, {
        detail: {
          title: "High-impact news test",
          body: "This is how a news alert is delivered with your current settings.",
          tab: "news",
          kind: "alert",
          test: true,
          toast: prefs.popup,
          desktop: prefs.desktop,
          sound: prefs.sound ? "notification" : undefined,
        },
      }),
    );
    setTested(true);
    window.setTimeout(() => setTested(false), 4000);
  };

  return (
    <div className="space-y-4">
      {/* ── News cards ──────────────────────────────────────────────── */}
      <Panel className="p-5 md:p-6" data-anchor="news-cards">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <LayoutGrid size={14} className="text-primary" />
            <span className="text-xs font-semibold uppercase tracking-wide">News cards</span>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={resetCards}
            disabled={!cardsReady}
            className="cursor-pointer rounded-xl"
          >
            <RotateCcw size={12} className="mr-1.5" /> Reset
          </Button>
        </div>
        <p className="mb-4 text-[10px] text-muted-foreground">
          How every story renders on the News tab. The same controls live under the
          feed&apos;s Customize button. Layout and visibility apply live; page size
          and sort apply when the feed next loads or refreshes.
        </p>

        <div className="space-y-3.5">
          <Row label="Cards per page">
            {[10, 20, 30, 50].map((n) => (
              <Choice key={n} active={cards.perPage === n} onClick={() => updateCards({ perPage: n })}>
                {n}
              </Choice>
            ))}
            <Choice
              active={!([10, 20, 30, 50] as number[]).includes(cards.perPage)}
              onClick={() => {
                const raw = window.prompt(`Cards per page (${1}–${MAX_PER_PAGE})`, String(cards.perPage));
                if (raw === null) return;
                const n = clampPerPage(raw);
                if (n) updateCards({ perPage: n });
              }}
              title="Custom page size"
            >
              Custom
            </Choice>
          </Row>

          <Row label="Sort">
            {(["importance", "newest", "oldest"] as const).map((s) => (
              <Choice key={s} active={cards.sort === s} onClick={() => updateCards({ sort: s })}>
                {s === "importance" ? "Critical first" : s[0].toUpperCase() + s.slice(1)}
              </Choice>
            ))}
          </Row>

          <Row label="Columns">
            {[1, 2, 3].map((n) => (
              <Choice
                key={n}
                active={cards.columns === n}
                onClick={() => updateCards({ columns: n as CardSettings["columns"] })}
              >
                {n === 1 ? "Single" : `${n} cols`}
              </Choice>
            ))}
            <span className="mx-1 w-px self-stretch bg-border/50" aria-hidden />
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Density</span>
            {(["compact", "cozy"] as const).map((d) => (
              <Choice key={d} active={cards.density === d} onClick={() => updateCards({ density: d })}>
                {d[0].toUpperCase() + d.slice(1)}
              </Choice>
            ))}
          </Row>

          <Row label="Summary">
            {([2, 3, 4, 0] as const).map((n) => (
              <Choice key={n} active={cards.summaryLines === n} onClick={() => updateCards({ summaryLines: n })}>
                {n === 0 ? "Full" : `${n} lines`}
              </Choice>
            ))}
          </Row>

          <Row label="Auto-refresh">
            <Choice active={cards.autoRefresh} onClick={() => updateCards({ autoRefresh: !cards.autoRefresh })}>
              {cards.autoRefresh ? "On" : "Off"}
            </Choice>
            {([30, 60, 120] as const).map((s) => (
              <Choice
                key={s}
                active={cards.refreshSec === s}
                disabled={!cards.autoRefresh}
                onClick={() => updateCards({ refreshSec: s })}
              >
                {s}s
              </Choice>
            ))}
          </Row>

          <SubSection title="Show on cards">
            <div className="flex flex-wrap gap-1.5">
              {([
                ["showSummary", "Summary"],
                ["showBadges", "Badges"],
                ["showTimestamp", "Timestamp"],
                ["showSentiment", "Sentiment"],
                ["showButtons", "Buttons"],
                ["glow", "Glow"],
              ] as [keyof CardSettings, string][]).map(([key, label]) => {
                const on = Boolean(cards[key]);
                return (
                  <Choice
                    key={key}
                    active={on}
                    onClick={() => updateCards({ [key]: !on } as Partial<CardSettings>)}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      {on && <Check size={9} />}
                      {label}
                    </span>
                  </Choice>
                );
              })}
            </div>
          </SubSection>
        </div>
      </Panel>

      {/* ── Pop-ups & notifications ─────────────────────────────────── */}
      <Panel className="p-5 md:p-6" data-anchor="news-notifications">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Bell size={14} className="text-primary" />
            <span className="text-xs font-semibold uppercase tracking-wide">Pop-ups &amp; notifications</span>
            {prefs.enabled ? (
              <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-emerald-400">
                <Check size={9} /> watching
              </span>
            ) : (
              <span className="text-[9px] uppercase tracking-widest text-muted-foreground">off</span>
            )}
          </div>
          <Toggle checked={prefs.enabled} onChange={(v) => update({ enabled: v })} />
        </div>
        <p className="mb-4 text-[10px] text-muted-foreground">
          High-impact stories and imminent macro releases from the local news scan.
          The header bell keeps a record while the watch is on, even when the
          pop-up, desktop notification and sound are off. Server-side channel pushes
          (Telegram, Discord, ntfy, email, webhook) live in Settings › Alerts.
        </p>

        <div className="space-y-2">
          <CardToggleRow
            label="In-app pop-up card"
            hint="A bottom-right card on any tab when a new high-impact story arrives."
            checked={prefs.popup}
            onChange={(v) => update({ popup: v })}
          />
          <CardToggleRow
            label="Desktop notification"
            hint="Native OS notification. Also requires the global desktop toggle under Settings › Alerts."
            checked={prefs.desktop}
            onChange={(v) => update({ desktop: v })}
          />
          <CardToggleRow
            label="Alert sound"
            hint="Plays the same alert cue as price alerts. Its voice and volume are under Settings › Sound."
            checked={prefs.sound}
            onChange={(v) => update({ sound: v })}
          />
          <CardToggleRow
            label="Upcoming economic releases"
            hint="Also announce high-impact releases inside the 90-minute horizon, not just published stories."
            checked={prefs.includeReleases}
            onChange={(v) => update({ includeReleases: v })}
          />
          <CardToggleRow
            label="Only my watchlist"
            hint={
              watchlistCount > 0
                ? `Only stories tagged with one of your ${watchlistCount} watchlist ticker${watchlistCount === 1 ? "" : "s"}.`
                : "Only stories tagged with a watchlist ticker. Your watchlist is empty, so this would silence story alerts."
            }
            checked={prefs.watchlistOnly}
            onChange={(v) => update({ watchlistOnly: v })}
          />
        </div>

        <div className="mt-4">
          <Row label="Minimum score">
            {NEWS_NOTIFY_MIN_SCORES.map((n) => (
              <Choice key={n} active={prefs.minScore === n} onClick={() => update({ minScore: n })}>
                {n === 75 ? "Critical only (75+)" : `High (${n}+)`}
              </Choice>
            ))}
          </Row>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            variant="outline"
            onClick={sendTest}
            disabled={!prefs.enabled || (!prefs.popup && !prefs.desktop && !prefs.sound)}
            className="cursor-pointer rounded-xl"
          >
            <SlidersHorizontal size={12} className="mr-1.5" /> Send test
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={resetPrefs}
            className="cursor-pointer rounded-xl"
          >
            <RotateCcw size={12} className="mr-1.5" /> Reset to defaults
          </Button>
          {tested && (
            <span className="text-[10px] text-muted-foreground">
              Test sent through the lanes you enabled.
            </span>
          )}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {[
            { icon: Newspaper, label: prefs.popup ? "Pop-up on" : "Pop-up off" },
            { icon: Monitor, label: prefs.desktop ? "Desktop on" : "Desktop off" },
            { icon: Volume2, label: prefs.sound ? "Sound on" : "Sound off" },
          ].map(({ icon: Icon, label }) => (
            <div
              key={label}
              className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-[10px] text-muted-foreground"
            >
              <Icon size={13} className="text-primary" /> {label}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
