'use client';

// The bot's private per-conversation memory. A bot keeps its own durable
// long-term memory keyed by `bot-<id>`, isolated from every other bot and from
// ordinary chat. This panel is READ-ONLY inspection plus an explicit "forget"
// (archive) control — it never invents a memory and never claims success before
// the server confirms it.

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';
import { Sparkles, Trash2 } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  forgetConversation,
  listConversationMemories,
} from '@/lib/harness/clients/eclipse-memory-browser';
import type { MemoryRecord } from '@/lib/harness/eclipse-memory-types';

export function BotMemorySection({ botId }: { botId: string }) {
  const t = useT();
  const conversationId = `bot-${botId}`;
  const [memories, setMemories] = useState<MemoryRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setMemories(await listConversationMemories(conversationId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'could not load memory');
      setMemories([]);
    }
  }, [conversationId]);

  useEffect(() => {
    void load();
  }, [load]);

  const forget = useCallback(async () => {
    if (!window.confirm(t('bots.memory.forgetConfirm'))) return;
    setBusy(true);
    try {
      const result = await forgetConversation(conversationId);
      await load();
      setError(
        result.archived.length
          ? t('bots.memory.forgotten', { count: result.archived.length })
          : t('bots.memory.empty'),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'forget failed');
    } finally {
      setBusy(false);
    }
  }, [conversationId, load, t]);

  return (
    <div className="space-y-3">
      <div className="glass-card-subtle flex items-start gap-2.5 rounded-xl p-4 text-xs text-muted-foreground">
        <Sparkles size={15} className="mt-0.5 shrink-0 text-primary/70" />
        <p className="min-w-0 break-words">{t('bots.memory.conversationNote')}</p>
      </div>

      {memories === null ? (
        <p className="px-1 text-xs text-muted-foreground">{t('common.loading')}</p>
      ) : memories.length === 0 ? (
        <p className="px-1 text-xs text-muted-foreground">{t('bots.memory.empty')}</p>
      ) : (
        <ul className="space-y-1.5">
          {memories.map((m) => (
            <li key={m.id} className="glass-card-subtle rounded-lg px-3 py-2">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                <span>{m.memoryType}</span>
                {m.subject ? <span className="normal-case text-foreground/70">· {m.subject}</span> : null}
                <span className="ml-auto normal-case">{m.status}</span>
              </div>
              <p className="mt-1 break-words text-xs text-foreground/90">{m.content}</p>
            </li>
          ))}
        </ul>
      )}

      {error ? <p className="px-1 text-xs text-destructive">{error}</p> : null}

      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-muted-foreground">
          {memories && memories.length ? t('bots.memory.count', { count: memories.length }) : ''}
        </span>
        <Button
          variant="ghost"
          size="sm"
          disabled={busy || !memories || memories.length === 0}
          onClick={() => void forget()}
        >
          <Trash2 size={14} className="mr-1.5" />
          {t('bots.memory.forget')}
        </Button>
      </div>
    </div>
  );
}
