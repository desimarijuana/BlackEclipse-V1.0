// ─── Dev command handlers ─────────────────────────────────────────────────────
// Extracted from command-handlers.ts to keep the dispatch table under its size
// ratchet: /rollback (file checkpoints).

import {
  fail,
  frontDoorError,
  type Handler,
} from "./command-handler-kit";
import { callout, dataTable, heading, keyValue, markdown } from "./command-render";

export const devHandlers: Record<string, Handler> = {
    "code.rollback": async (_ctx, _spec, args, deps) => {
    const raw = args.positionals.checkpointId;
    const checkpointId = (Array.isArray(raw) ? raw[0] : raw)?.trim();
    if (!checkpointId) {
      const { ok, status, data } = await deps.frontDoor.request("/api/code/checkpoints?limit=20", {
        method: "GET",
      });
      if (!ok) return fail("CHECKPOINT_FAILED", frontDoorError(data, status));
      const items = (data as { checkpoints?: Array<Record<string, unknown>> }).checkpoints ?? [];
      if (!items.length) {
        return {
          status: "completed",
          blocks: [
            heading("File snapshots", 2),
            markdown("No snapshots yet. Eclipse takes one before the first file change."),
          ],
        };
      }
      return {
        status: "completed",
        blocks: [
          heading("File snapshots", 2),
          dataTable(
            "Recent",
            [
              { key: "id", label: "Snapshot" },
              { key: "reason", label: "Reason" },
              { key: "files", label: "Files" },
            ],
            items.map((item) => ({
              id: String(item.id ?? ""),
              reason: String(item.reason ?? "before-write"),
              files: String(item.files ?? 0),
            })),
          ),
          markdown("Run `/rollback <snapshot-id>` to see the diff, then add `--all` to restore it."),
        ],
      };
    }
    const restoreAll = args.flags.all === true;
    const pathsFlag = typeof args.flags.paths === "string" ? args.flags.paths : "";
    const paths = pathsFlag
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);
    if (restoreAll || paths.length) {
      const { ok, status, data } = await deps.frontDoor.request(
        `/api/code/checkpoints/${encodeURIComponent(checkpointId)}/restore`,
        { method: "POST", body: { all: restoreAll, ...(paths.length ? { paths } : {}) } },
      );
      if (!ok) return fail("CHECKPOINT_RESTORE_FAILED", frontDoorError(data, status));
      const body = data as {
        restored?: string[];
        skipped?: string[];
        preRestoreId?: string | null;
      };
      return {
        status: "completed",
        blocks: [
          heading("Restored", 2),
          keyValue("Snapshot", [
            { label: "Restored", value: String(body.restored?.length ?? 0) },
            { label: "Skipped", value: String(body.skipped?.length ?? 0) },
            { label: "Undo point", value: String(body.preRestoreId ?? "—") },
          ]),
          callout(
            "note",
            "This restore is undoable",
            body.preRestoreId
              ? `A pre-restore snapshot was saved as ${body.preRestoreId}.`
              : "No pre-restore snapshot was available.",
          ),
        ],
      };
    }
    const { ok, status, data } = await deps.frontDoor.request(
      `/api/code/checkpoints/${encodeURIComponent(checkpointId)}/diff`,
      { method: "GET" },
    );
    if (!ok) return fail("CHECKPOINT_DIFF_FAILED", frontDoorError(data, status));
    const unified = String((data as { unified?: string }).unified ?? "");
    return {
      status: "completed",
      blocks: [
        heading(`Changes since ${checkpointId}`, 2),
        markdown(unified.trim() || "(no differences)"),
        markdown("Confirm a full restore with `/rollback " + checkpointId + " --all`."),
      ],
    };
  },

};
