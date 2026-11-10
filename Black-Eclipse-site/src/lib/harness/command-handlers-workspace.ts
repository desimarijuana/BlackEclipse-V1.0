// ─── Workspace command handlers (read-only domain surfaces) ───────────────────
// Alerts, news, theses, journal, jobs, artifacts, sessions, git and run
// cancellation. These handlers only call the app's existing front doors; they
// own no storage and never invent a row the API did not return.

import { callout, dataTable, heading, keyValue, markdown } from "./command-render";
import { fail, frontDoorError, invalid, str, type Handler } from "./command-handler-kit";
import type { CommandDeps } from "./command-router";
import type { ResponseBlock } from "@/lib/response/contract";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    : [];
}

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function short(value: unknown, max = 80): string {
  const raw = text(value);
  return raw.length > max ? `${raw.slice(0, max - 1)}…` : raw;
}

function when(value: unknown): string {
  if (typeof value !== "string" || !value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return short(value, 24);
  return date.toISOString().replace("T", " ").slice(0, 16);
}

function bytes(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

async function get(
  deps: CommandDeps,
  path: string,
  timeoutMs = 30_000,
): Promise<{ ok: boolean; status: number; data: unknown }> {
  return deps.frontDoor.request(path, { timeoutMs });
}

const alerts: Handler = async (_ctx, _spec, _args, deps) => {
  const { ok, status, data } = await get(deps, "/api/alerts");
  if (!ok) return fail("ALERTS_FAILED", frontDoorError(data, status));
  const payload = asRecord(data);
  const rows = asRows(payload.alerts);
  const blocks: ResponseBlock[] = [
    heading("Alerts", 2),
    markdown(`${rows.length} watch${rows.length === 1 ? "" : "es"} · ${text(payload.running, "0")} monitor(s) running.`),
  ];
  if (!rows.length) {
    blocks.push(callout("note", "No watches", "Create one in Price Alerts, then run `/alerts` again."));
    return { status: "completed", blocks };
  }
  blocks.push(
    dataTable(
      "Watches",
      [
        { key: "name", label: "Name" },
        { key: "symbols", label: "Symbols" },
        { key: "status", label: "Status" },
        { key: "lastFiredAt", label: "Last fired" },
      ],
      rows.slice(0, 50).map((row) => ({
        name: short(row.name, 60),
        symbols: Array.isArray(row.symbols) ? row.symbols.join(", ") : text(row.symbols),
        status: text(row.status ?? (row.active ? "active" : "inactive")),
        lastFiredAt: when(row.lastFiredAt),
      })),
    ),
  );
  return { status: "completed", blocks };
};

const news: Handler = async (_ctx, _spec, args, deps) => {
  const query = (Array.isArray(args.positionals.query) ? (args.positionals.query as string[]) : [])
    .join(" ")
    .trim();
  const tickerFlag = typeof args.flags.ticker === "string" ? args.flags.ticker.trim().toUpperCase() : "";
  const sortFlag = args.flags.sort === "importance" ? "importance" : "newest";
  const params = new URLSearchParams({ limit: "12", sort: sortFlag });
  if (tickerFlag) params.set("ticker", tickerFlag);
  // Only an uppercase ticker-shaped token is treated as a ticker; a lowercase
  // word like "rates" or "nvidia" is a free-text search instead.
  else if (/^[A-Z][A-Z0-9.=]{0,9}$/.test(query)) params.set("ticker", query);
  else if (query) params.set("q", query);

  const { ok, status, data } = await get(deps, `/api/news?${params.toString()}`, 60_000);
  if (!ok) return fail("NEWS_FAILED", frontDoorError(data, status));
  const payload = asRecord(data);
  const rows = asRows(payload.news);
  const blocks: ResponseBlock[] = [heading("News", 2)];
  if (!rows.length) {
    blocks.push(
      callout(
        "note",
        "No news items",
        "Nothing matched. The feed may be disabled in Setup or still ingesting; `/news` never fabricates a headline.",
      ),
    );
    return { status: "completed", blocks };
  }
  blocks.push(
    markdown(
      `${rows.length} item${rows.length === 1 ? "" : "s"} from ${text(payload.source, "the local news store")}.`,
    ),
    dataTable(
      "Latest",
      [
        { key: "headline", label: "Headline" },
        { key: "ticker", label: "Ticker" },
        { key: "sentiment", label: "Sentiment" },
        { key: "source", label: "Source" },
        { key: "time", label: "Time" },
      ],
      rows.slice(0, 12).map((row) => ({
        headline: short(row.headline, 160),
        ticker: text(row.ticker),
        sentiment: text(row.sentiment),
        source: short(row.source, 40),
        time: when(row.timestamp),
      })),
    ),
  );
  return { status: "completed", blocks };
};

const theses: Handler = async (_ctx, _spec, args, deps) => {
  const symbol = str(args.positionals.symbol).trim().toUpperCase();
  const path = symbol ? `/api/theses?symbol=${encodeURIComponent(symbol)}` : "/api/theses";
  const { ok, status, data } = await get(deps, path);
  if (!ok) return fail("THESES_FAILED", frontDoorError(data, status));
  const rows = asRows(asRecord(data).theses);
  const blocks: ResponseBlock[] = [
    heading("Theses", 2),
    markdown(symbol ? `Filtered to **${symbol}**.` : `${rows.length} thesis row${rows.length === 1 ? "" : "s"}.`),
  ];
  if (!rows.length) {
    blocks.push(callout("note", "No theses", "Create one in the Theses workspace, then run `/theses` again."));
    return { status: "completed", blocks };
  }
  blocks.push(
    dataTable(
      "Tracked theses",
      [
        { key: "symbol", label: "Symbol" },
        { key: "title", label: "Title" },
        { key: "status", label: "Status" },
        { key: "review", label: "Review" },
        { key: "updated", label: "Updated" },
      ],
      rows.slice(0, 50).map((row) => ({
        symbol: text(row.symbol),
        title: short(row.title, 80),
        status: text(row.status),
        review: when(row.reviewDate),
        updated: when(row.updatedAt ?? row.createdAt),
      })),
    ),
  );
  return { status: "completed", blocks };
};

const journal: Handler = async (_ctx, _spec, args, deps) => {
  const filter = str(args.positionals.filter).trim().toLowerCase() || "all";
  if (!["all", "open", "closed"].includes(filter)) {
    return invalid("JOURNAL_FILTER", "Usage: `/journal [all|open|closed]`.");
  }
  const { ok, status, data } = await get(deps, "/api/journal/trades", 60_000);
  if (!ok) return fail("JOURNAL_FAILED", frontDoorError(data, status));
  const all = asRows(asRecord(data).trades);
  const rows = all.filter((row) => {
    if (filter === "open") return row.exit === null || row.exit === undefined;
    if (filter === "closed") return row.exit !== null && row.exit !== undefined;
    return true;
  });
  const blocks: ResponseBlock[] = [heading("Journal", 2)];
  if (!rows.length) {
    blocks.push(callout("note", "No trades", `No ${filter === "all" ? "" : `${filter} `}trades are recorded.`));
    return { status: "completed", blocks };
  }
  const closed = rows.filter((row) => row.exit !== null && row.exit !== undefined);
  const net = closed.reduce((sum, row) => {
    const value = Number(row.pnl);
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);
  blocks.push(
    keyValue("Recorded trades", [
      { label: "Rows", value: rows.length },
      { label: "Closed", value: closed.length },
      { label: "Net P&L (recorded)", value: net.toFixed(2) },
    ]),
    dataTable(
      "Trades",
      [
        { key: "symbol", label: "Symbol" },
        { key: "direction", label: "Side" },
        { key: "entry", label: "Entry" },
        { key: "exit", label: "Exit" },
        { key: "quantity", label: "Qty" },
        { key: "pnl", label: "P&L" },
        { key: "opened", label: "Opened" },
      ],
      rows.slice(0, 50).map((row) => ({
        symbol: text(row.symbol),
        direction: text(row.direction),
        entry: text(row.entry),
        exit: text(row.exit),
        quantity: text(row.quantity),
        pnl: text(row.pnl),
        opened: when(row.entryTime ?? row.openedAt),
      })),
    ),
    markdown("P&L is the sum of the journal's recorded rows, not a broker statement."),
  );
  return { status: "completed", blocks };
};

const jobs: Handler = async (_ctx, _spec, _args, deps) => {
  const { ok, status, data } = await get(deps, "/api/jobs");
  if (!ok) return fail("JOBS_FAILED", frontDoorError(data, status));
  const rows = asRows(asRecord(data).jobs);
  const blocks: ResponseBlock[] = [heading("Jobs", 2)];
  if (!rows.length) {
    blocks.push(callout("note", "No jobs", "Create a scheduled or watched job in the Jobs screen."));
    return { status: "completed", blocks };
  }
  blocks.push(
    markdown(`${rows.filter((row) => row.enabled).length} of ${rows.length} enabled.`),
    dataTable(
      "Scheduled work",
      [
        { key: "name", label: "Name" },
        { key: "kind", label: "Kind" },
        { key: "schedule", label: "Schedule" },
        { key: "enabled", label: "Enabled" },
        { key: "last", label: "Last run" },
        { key: "failures", label: "Failures" },
      ],
      rows.slice(0, 50).map((row) => ({
        name: short(row.name, 60),
        kind: text(row.kind),
        schedule: text(row.cron ?? (row.intervalSeconds ? `every ${row.intervalSeconds}s` : row.watchPath)),
        enabled: row.enabled ? "yes" : "no",
        last: when(row.lastRunAt),
        failures: text(row.consecutiveFailures, "0"),
      })),
    ),
    markdown(`Run one with \`/jobs\` → **Jobs** screen; this command is read-only.`),
  );
  return { status: "completed", blocks };
};

const artifacts: Handler = async (_ctx, _spec, _args, deps) => {
  const { ok, status, data } = await get(deps, "/api/artifacts?limit=15", 60_000);
  if (!ok) return fail("ARTIFACTS_FAILED", frontDoorError(data, status));
  const payload = asRecord(data);
  const rows = asRows(payload.artifacts);
  const blocks: ResponseBlock[] = [heading("Artifacts", 2)];
  if (!rows.length) {
    blocks.push(callout("note", "No artifacts", "Artifacts created by runs and Canvas appear here."));
    return { status: "completed", blocks };
  }
  blocks.push(
    markdown(`${text(payload.total, String(rows.length))} total${payload.hasMore ? " · more available" : ""}.`),
    dataTable(
      "Recent artifacts",
      [
        { key: "name", label: "Name" },
        { key: "category", label: "Category" },
        { key: "mime", label: "Type" },
        { key: "size", label: "Size" },
        { key: "updated", label: "Updated" },
      ],
      rows.map((row) => ({
        name: short(row.name, 70),
        category: text(row.category),
        mime: short(row.mimeType ?? row.mime_type, 40),
        size: bytes(row.sizeBytes ?? row.size_bytes),
        updated: when(row.updatedAt ?? row.createdAt),
      })),
    ),
  );
  return { status: "completed", blocks };
};

const sessions: Handler = async (_ctx, _spec, _args, deps) => {
  const { ok, status, data } = await get(deps, "/api/sessions?limit=12", 60_000);
  if (!ok) return fail("SESSIONS_FAILED", frontDoorError(data, status));
  const payload = asRecord(data);
  const rows = asRows(payload.sessions);
  const blocks: ResponseBlock[] = [heading("Sessions", 2)];
  if (!rows.length) {
    blocks.push(callout("note", "No sessions", "Named chat sessions appear here once they are created."));
    return { status: "completed", blocks };
  }
  blocks.push(
    markdown(`${text(payload.total, String(rows.length))} total${payload.hasMore ? " · more available" : ""}.`),
    dataTable(
      "Recent sessions",
      [
        { key: "title", label: "Title" },
        { key: "status", label: "Status" },
        { key: "updated", label: "Updated" },
        { key: "id", label: "Id" },
      ],
      rows.map((row) => ({
        title: short(row.title ?? row.name ?? row.id, 70),
        status: text(row.status),
        updated: when(row.updatedAt ?? row.updated_at),
        id: short(row.id, 40),
      })),
    ),
  );
  return { status: "completed", blocks };
};

const git: Handler = async (_ctx, _spec, args, deps) => {
  const action = str(args.positionals.action).trim().toLowerCase() || "status";
  if (!["status", "diff", "log"].includes(action)) {
    return invalid("GIT_ACTION", "Usage: `/git [status|diff|log] [--staged]`.");
  }
  const staged = args.flags.staged === true;
  const query = action === "diff" && staged ? "action=diff&staged=1" : `action=${action}`;
  const { ok, status, data } = await get(deps, `/api/git?${query}`, 60_000);
  if (!ok) return fail("GIT_FAILED", frontDoorError(data, status));
  const payload = asRecord(data);

  if (action === "diff") {
    const diff = text(payload.diff, "");
    return {
      status: "completed",
      blocks: [
        heading("Git diff", 2),
        ...(diff
          ? [markdown("````diff\n" + diff.slice(0, 18_000) + "\n````")]
          : [callout("note", "No diff", staged ? "Nothing is staged." : "The working tree has no changes.")]),
      ],
    };
  }

  if (action === "log") {
    const rows = asRows(payload.commits);
    return {
      status: "completed",
      blocks: [
        heading("Git log", 2),
        ...(rows.length
          ? [
              dataTable(
                "Commits",
                [
                  { key: "hash", label: "Hash" },
                  { key: "subject", label: "Subject" },
                  { key: "author", label: "Author" },
                  { key: "date", label: "Date" },
                ],
                rows.map((row) => ({
                  hash: short(row.shortHash ?? row.hash, 12),
                  subject: short(row.subject, 80),
                  author: short(row.author, 30),
                  date: when(row.date),
                })),
              ),
            ]
          : [markdown("No commits reported.")]),
      ],
    };
  }

  const s = asRecord(payload.status);
  const summary = asRecord(s.summary);
  const changed: Array<Record<string, unknown>> = [
    ...asRows(s.staged).map((row) => ({ path: row.path, state: `staged ${text(row.status)}` })),
    ...asRows(s.unstaged).map((row) => ({ path: row.path, state: `unstaged ${text(row.status)}` })),
    ...(Array.isArray(s.untracked) ? s.untracked : []).map((path) => ({ path, state: "untracked" })),
  ];
  const blocks: ResponseBlock[] = [
    heading("Git status", 2),
    keyValue("Repository", [
      { label: "Branch", value: text(s.branch) },
      { label: "Upstream", value: text(s.upstream) },
      { label: "Ahead / behind", value: `${text(s.ahead, "0")} / ${text(s.behind, "0")}` },
      { label: "Clean", value: s.clean ? "yes" : "no" },
      { label: "Changed", value: `${text(summary.staged, "0")} staged · ${text(summary.unstaged, "0")} unstaged · ${text(summary.untracked, "0")} untracked` },
    ]),
  ];
  if (changed.length) {
    blocks.push(
      dataTable(
        "Files",
        [
          { key: "path", label: "Path" },
          { key: "state", label: "State" },
        ],
        changed.slice(0, 80),
      ),
    );
  }
  return { status: "completed", blocks };
};

const stop: Handler = async (_ctx, _spec, args, deps) => {
  const runId = str(args.positionals.runId).trim();
  if (runId) {
    const res = await deps.frontDoor.request(`/api/harness/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      timeoutMs: 30_000,
    });
    if (!res.ok) return fail("STOP_FAILED", frontDoorError(res.data, res.status));
    const result = asRecord(res.data);
    return {
      status: "completed",
      blocks: [
        heading("Run cancellation", 2),
        keyValue("Result", [
          { label: "Run", value: runId },
          { label: "Cancelled", value: result.cancelled ? "yes" : "no" },
        ]),
        markdown(text(result.message, "Cancellation requested.")),
      ],
    };
  }

  const { ok, status, data } = await get(deps, "/api/harness/runs");
  if (!ok) return fail("RUNS_FAILED", frontDoorError(data, status));
  const active = asRows(asRecord(data).runs).filter(
    (run) => run.status === "running" || run.status === "created",
  );
  const blocks: ResponseBlock[] = [heading("Active runs", 2)];
  if (!active.length) {
    blocks.push(callout("note", "Nothing active", "No run is currently running or queued."));
  } else {
    blocks.push(
      markdown("Cancel one with `/stop <runId>`."),
      dataTable(
        "Runs",
        [
          { key: "id", label: "Run" },
          { key: "agent", label: "Agent" },
          { key: "status", label: "Status" },
          { key: "model", label: "Model" },
          { key: "created", label: "Created" },
        ],
        active.slice(0, 25).map((run) => ({
          id: short(run.id, 40),
          agent: short(run.agentId, 30),
          status: text(run.status),
          model: short(run.model, 30),
          created: when(run.createdAt ?? run.startedAt),
        })),
      ),
    );
  }
  return { status: "completed", blocks };
};

const history: Handler = async (_ctx, _spec, args, deps) => {
  const raw = Number(args.positionals.limit);
  const limit = Number.isFinite(raw) ? Math.max(1, Math.min(200, Math.floor(raw))) : 20;
  const events = await deps.audit.read(limit);
  const blocks: ResponseBlock[] = [
    heading("Command history", 2),
    markdown(`${events.length} entr${events.length === 1 ? "y" : "ies"}, newest first.`),
  ];
  if (!events.length) {
    blocks.push(callout("note", "No history", "The command audit is empty; run a command first."));
    return { status: "completed", blocks };
  }
  blocks.push(
    dataTable(
      "Executions",
      [
        { key: "time", label: "Time" },
        { key: "command", label: "Command" },
        { key: "status", label: "Status" },
        { key: "actor", label: "Actor" },
        { key: "risk", label: "Risk" },
        { key: "duration", label: "Duration" },
      ],
      events.map((event) => ({
        time: when(event.at),
        command: `/${event.command}`,
        status: event.status,
        actor: event.actor,
        risk: event.risk ?? "—",
        duration: `${event.durationMs} ms`,
      })),
    ),
    markdown("This is the redacted audit — command id/status/duration only, never output or arguments."),
  );
  return { status: "completed", blocks };
};

export const workspaceHandlers: Record<string, Handler> = {
  "markets.alerts": alerts,
  "markets.news": news,
  "portfolio.theses": theses,
  "portfolio.journal": journal,
  "runtime.jobs": jobs,
  "runtime.artifacts": artifacts,
  "runtime.sessions": sessions,
  "dev.git": git,
  "runtime.stop": stop,
  "runtime.history": history,
};
