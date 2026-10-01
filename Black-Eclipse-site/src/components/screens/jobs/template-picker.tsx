'use client';

// ── The finance job library (Phase 6) ───────────────────────────────────────
// One-click templates. The user answers "which tickers?" / "which folder?" and
// their job is built. They never author a definition or meet a cron expression.

import { useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import type { JobTemplateView } from '@/lib/harness/jobs-browser';

export interface TemplatePickerProps {
  templates: JobTemplateView[];
  onUse: (templateId: string, params: Record<string, string>) => void;
}

export function TemplatePicker({ templates, onUse }: TemplatePickerProps) {
  const t = useT();
  const [openId, setOpenId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  if (templates.length === 0) return null;

  return (
    <section className="glass-card rounded-2xl p-3">
      <h3 className="mb-2 text-[13px] font-medium text-foreground">{t('jobs.library.title')}</h3>
      <ul className="grid gap-2 sm:grid-cols-2">
        {templates.map((template) => {
          const open = openId === template.id;
          return (
            <li key={template.id} className="glass-card-subtle rounded-xl p-2.5">
              <p className="text-[12px] font-medium text-foreground">{template.name}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">{template.description}</p>
              {template.parameters.length === 0 ? (
                <button
                  type="button"
                  onClick={() => onUse(template.id, {})}
                  className="glass-button mt-2 rounded-lg px-2.5 py-1 text-[11px] text-foreground"
                >
                  {t('jobs.library.use')}
                </button>
              ) : open ? (
                <div className="mt-2 space-y-1.5">
                  {template.parameters.map((param) => (
                    <label key={param.key} className="block text-[11px] text-muted-foreground">
                      {t('jobs.library.answer', { label: param.label })}
                      <input
                        value={answers[param.key] ?? ''}
                        onChange={(e) => setAnswers((prev) => ({ ...prev, [param.key]: e.target.value }))}
                        placeholder={param.example ? t('jobs.library.placeholder', { example: param.example }) : ''}
                        className="mt-1 w-full rounded-lg bg-background/60 px-2 py-1 text-[12px] text-foreground outline-none"
                      />
                    </label>
                  ))}
                  <button
                    type="button"
                    onClick={() => onUse(template.id, answers)}
                    className="glass-button rounded-lg px-2.5 py-1 text-[11px] text-foreground"
                  >
                    {t('jobs.library.use')}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => { setOpenId(template.id); setAnswers({}); }}
                  className="glass-button mt-2 rounded-lg px-2.5 py-1 text-[11px] text-foreground"
                >
                  {t('jobs.library.use')}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
