"use client";

// A compact checkpoint control for a conversation: save the current state, list
// saved points, and restore one. Like an editor's save points — a bad turn can
// be rolled back to a known-good state.
//
// The conversation lives in the browser; the server only stores snapshots, so
// this component sends the current messages to save and applies a returned
// snapshot to restore.

import React, { useCallback, useEffect, useState } from "react";
import { BookmarkPlus, History, RotateCcw, Trash2, Loader2 } from "@/lib/icons";
import { cn } from "@/lib/utils";
import {
  createCheckpoint,
  deleteCheckpoint,
  listCheckpoints,
  readCheckpoint,
} from "@/lib/chat/session-client";
import type { Checkpoint } from "@/lib/chat/session-types";
import type { Message } from "@/types/chat";

export interface CheckpointBarProps {
  chatId: string | null;
  messages: Message[];
  onRestore: (messages: Message[]) => void;
  className?: string;
}

export function CheckpointBar({ chatId, messages, onRestore, className }: CheckpointBarProps) {
  const [open, setOpen] = useState(false);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!chatId) return;
    try {
      setCheckpoints(await listCheckpoints(chatId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load checkpoints");
    }
  }, [chatId]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const save = async () => {
    if (!chatId || messages.length === 0 || busy) return;
    setBusy(true);
    setError("");
    try {
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      const label = lastUser ? `After: ${lastUser.content.slice(0, 48)}` : "Checkpoint";
      await createCheckpoint(
        chatId,
        label,
        messages.map((m) => ({ id: m.id, role: m.role, content: m.content }))
      );
      await refresh();
      setOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save checkpoint");
    } finally {
      setBusy(false);
    }
  };

  const restore = async (id: string) => {
    if (!chatId || busy) return;
    setBusy(true);
    setError("");
    try {
      const snapshot = await readCheckpoint(chatId, id);
      const restored: Message[] = snapshot.messages.map((m) => ({
        id: m.id,
        role: m.role === "user" ? "user" : "assistant",
        content: m.content,
      }));
      onRestore(restored);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not restore checkpoint");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!chatId) return;
    try {
      await deleteCheckpoint(chatId, id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete checkpoint");
    }
  };

  return (
    <div className={cn("relative", className)} data-nodrag>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={save}
          disabled={!chatId || messages.length === 0 || busy}
          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:text-primary disabled:cursor-default disabled:opacity-30 cursor-pointer"
          title="Save a checkpoint of this conversation"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <BookmarkPlus size={13} />}
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={!chatId}
          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:text-primary disabled:cursor-default disabled:opacity-30 cursor-pointer"
          title="Checkpoints"
        >
          <History size={13} />
        </button>
      </div>

      {open && (
        <div className="absolute right-0 top-8 z-10 max-h-[min(50vh,320px)] w-72 overflow-y-auto rounded-xl border border-white/12 dark:border-white/8 glass-card-strong p-2 shadow-2xl shadow-black/50">
          {error && <p className="px-2 py-1 text-[10px] text-rose-400">{error}</p>}
          {checkpoints.length === 0 ? (
            <p className="px-2 py-2 text-[11px] text-muted-foreground">
              No checkpoints yet. Save one to roll back to this point later.
            </p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {checkpoints.map((cp) => (
                <li key={cp.id} className="group flex items-center gap-1 rounded-lg px-1.5 py-1 hover:bg-white/5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[11px] font-medium text-foreground">{cp.label}</p>
                    <p className="truncate text-[9px] text-muted-foreground">
                      {cp.messageCount} turns · {new Date(cp.createdAt).toLocaleString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => restore(cp.id)}
                    className="rounded p-1 text-muted-foreground hover:text-primary cursor-pointer"
                    title="Restore this checkpoint"
                  >
                    <RotateCcw size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(cp.id)}
                    className="rounded p-1 text-muted-foreground hover:text-rose-400 cursor-pointer"
                    title="Delete"
                  >
                    <Trash2 size={11} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
