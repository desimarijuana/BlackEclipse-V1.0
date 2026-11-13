'use client';

// ── Settings › Voice › Voice input ──────────────────────────────────────────
// Dictation configuration: preferred engine, language, vocabulary hint, clip
// cap, and the OpenAI-compatible transcription endpoint. The provider key is
// never edited here — it lives in the shared vault (Settings › AI), so this
// pane can only report whether one is configured.

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, Check, Loader2, Mic, RefreshCcw } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { browserRecognitionAvailable } from '@/lib/voice/browser-recognition';
import { resetVoiceConfigCache } from '@/lib/voice/client';
import { useVoiceInputStore } from '@/lib/voice/store';
import {
  TRANSCRIBE_PRESETS,
  describeVoiceEngine,
  type TranscribeProvider,
  type VoiceServerConfig,
} from '@/lib/voice/types';
import { Field, Panel, SubSection } from './settings-ui';

const LANGUAGES: Array<{ value: string; label: string }> = [
  { value: '', label: 'Automatic (speaker’s language)' },
  { value: 'en', label: 'English' },
  { value: 'en-US', label: 'English (US)' },
  { value: 'en-GB', label: 'English (UK)' },
  { value: 'ur', label: 'Urdu' },
  { value: 'hi', label: 'Hindi' },
  { value: 'ar', label: 'Arabic' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'zh', label: 'Chinese' },
  { value: 'ja', label: 'Japanese' },
];

const ENGINE_ITEMS = [
  { value: 'auto', label: 'Automatic' },
  { value: 'whisper', label: 'Whisper (server)' },
  { value: 'browser', label: 'Browser recognition' },
];

const PROVIDER_ITEMS = [
  { value: 'auto', label: 'Automatic (on-device, or a key)' },
  { value: 'local', label: 'On this device (no key)' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'groq', label: 'Groq' },
  { value: 'custom', label: 'Custom endpoint' },
];

const MAX_CLIP_ITEMS = [
  { value: '30', label: '30 seconds' },
  { value: '60', label: '60 seconds' },
  { value: '120', label: '2 minutes' },
];

const LANGUAGE_ITEMS = LANGUAGES.map((language) => ({
  value: language.value || 'auto',
  label: language.label,
}));

interface ConfigPayload {
  config?: VoiceServerConfig;
  stored?: { provider?: TranscribeProvider; baseUrl?: string; model?: string };
  error?: string;
}

export function VoiceInputSettings() {
  const prefs = useVoiceInputStore((store) => store.prefs);
  const hydrate = useVoiceInputStore((store) => store.hydrate);
  const setEngine = useVoiceInputStore((store) => store.setEngine);
  const setLanguage = useVoiceInputStore((store) => store.setLanguage);
  const setPrompt = useVoiceInputStore((store) => store.setPrompt);
  const setMaxSeconds = useVoiceInputStore((store) => store.setMaxSeconds);

  const [server, setServer] = useState<VoiceServerConfig | null>(null);
  const [provider, setProvider] = useState<TranscribeProvider>('auto');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/voice/config', { cache: 'no-store' });
      const body = (await res.json().catch(() => ({}))) as ConfigPayload;
      if (!res.ok || !body.config) throw new Error(body.error || 'Could not read voice settings');
      setServer(body.config);
      setProvider(body.stored?.provider ?? 'auto');
      setBaseUrl(body.stored?.baseUrl ?? '');
      setModel(body.stored?.model ?? '');
      setMessage(null);
    } catch (err) {
      setMessage({ kind: 'error', text: err instanceof Error ? err.message : 'Could not read voice settings' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const browserAvailable = browserRecognitionAvailable();
  const activeEngine = describeVoiceEngine(prefs.engine, server?.ready === true, browserAvailable);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch('/api/voice/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          baseUrl: baseUrl.trim() || undefined,
          model: model.trim() || undefined,
        }),
      });
      const body = (await res.json().catch(() => ({}))) as ConfigPayload;
      if (!res.ok || !body.config) throw new Error(body.error || 'Could not save voice settings');
      setServer(body.config);
      resetVoiceConfigCache();
      setMessage({ kind: 'ok', text: 'Saved. The composer will use this on the next dictation.' });
    } catch (err) {
      setMessage({ kind: 'error', text: err instanceof Error ? err.message : 'Could not save voice settings' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel className="p-5 md:p-6 space-y-5">
      <SubSection
        icon={Mic}
        title="Voice input (dictation)"
        description="Speak a prompt into the composer. Audio is transcribed once and discarded — it is never stored, and only the resulting text lands in the prompt."
      >
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/30 bg-white/[0.03] px-3 py-2 text-[11px]">
          {loading ? (
            <Loader2 size={13} className="animate-spin text-muted-foreground" />
          ) : activeEngine === 'whisper' ? (
            <Check size={13} className="text-emerald-300" />
          ) : activeEngine === 'browser' ? (
            <Check size={13} className="text-emerald-300" />
          ) : (
            <AlertCircle size={13} className="text-amber-300" />
          )}
          <span className="text-muted-foreground">
            {loading
              ? 'Checking transcription readiness…'
              : activeEngine === 'whisper'
                ? server?.provider === 'local'
                  ? `On-device Whisper ready — ${server?.model ?? 'base.en'} (no key)`
                  : `Whisper ready — ${server?.provider ?? 'configured'} · ${server?.model ?? ''}`
                : activeEngine === 'browser'
                  ? 'Browser dictation — no key needed'
                  : 'Not available — the on-device engine is missing from the Python runtime (run npm run setup:python)'}
          </span>
          {server && activeEngine === 'whisper' && (
            <span className="rounded-full border border-border/40 px-1.5 py-px text-[9px] text-muted-foreground/80">
              {server.keyConfigured ? 'key configured' : 'keyless endpoint'}
            </span>
          )}
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="ml-auto inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
            title="Re-check the transcription provider"
          >
            <RefreshCcw size={11} /> Refresh
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Preferred engine"
            hint="Automatic prefers Whisper when a provider is configured, otherwise the browser."
          >
            <Select items={ENGINE_ITEMS} value={prefs.engine} onValueChange={(value) => setEngine(value as typeof prefs.engine)}>
              <SelectTrigger className="h-auto w-full justify-between py-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Automatic</SelectItem>
                <SelectItem value="whisper">Whisper (server)</SelectItem>
                <SelectItem value="browser">Browser recognition</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field label="Language" hint="A hint improves accuracy; Automatic uses the speaker’s language.">
            <Select
              items={LANGUAGE_ITEMS}
              value={prefs.language || 'auto'}
              onValueChange={(value) => setLanguage(!value || value === 'auto' ? '' : value)}
            >
              <SelectTrigger className="h-auto w-full justify-between py-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {LANGUAGES.map((language) => (
                  <SelectItem key={language.value || 'auto'} value={language.value || 'auto'}>
                    {language.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Maximum clip" hint="Dictation stops automatically at this length.">
            <Select
              items={MAX_CLIP_ITEMS}
              value={String(prefs.maxSeconds)}
              onValueChange={(value) => setMaxSeconds(Number(value) || 60)}
            >
              <SelectTrigger className="h-auto w-full justify-between py-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30 seconds</SelectItem>
                <SelectItem value="60">60 seconds</SelectItem>
                <SelectItem value="120">2 minutes</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field
            label="Transcription provider"
            hint="Automatic uses a configured cloud key when there is one, otherwise the on-device engine (no key, works offline after a one-time model download). Custom covers a local whisper.cpp server."
          >
            <Select items={PROVIDER_ITEMS} value={provider} onValueChange={(value) => setProvider(value as TranscribeProvider)}>
              <SelectTrigger className="h-auto w-full justify-between py-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Automatic (on-device, or a key)</SelectItem>
                <SelectItem value="local">On this device (no key)</SelectItem>
                <SelectItem value="openai">OpenAI</SelectItem>
                <SelectItem value="groq">Groq</SelectItem>
                <SelectItem value="custom">Custom endpoint</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>

        {provider === 'custom' && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Base URL" hint="e.g. http://127.0.0.1:8080/v1 — keyless local endpoints are allowed.">
              <Input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="http://127.0.0.1:8080/v1"
                spellCheck={false}
              />
            </Field>
            <Field label="Model" hint={TRANSCRIBE_PRESETS.custom.model}>
              <Input
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder={TRANSCRIBE_PRESETS.custom.model}
                spellCheck={false}
              />
            </Field>
          </div>
        )}

        <Field
          label="Vocabulary hint"
          hint="Sent to Whisper to bias tickers and finance terms. Browser recognition ignores it."
        >
          <textarea
            value={prefs.prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={3}
            maxLength={900}
            className="w-full resize-y rounded-xl border border-border/40 bg-transparent px-3 py-2 text-xs leading-relaxed text-foreground focus:outline-none focus:border-primary/40"
          />
        </Field>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" onClick={() => void save()} disabled={saving}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : null}
            Save transcription settings
          </Button>
          <p className="text-[10px] text-muted-foreground/70">
            Keys live in Settings › AI (OpenAI, Groq) or the custom transcription key. Audio never leaves
            this machine unless the selected provider is remote.
          </p>
        </div>

        {message && (
          <p
            role="status"
            className={
              message.kind === 'ok'
                ? 'text-[10px] text-emerald-300/90'
                : 'text-[10px] text-rose-300/90'
            }
          >
            {message.text}
          </p>
        )}
        {prefs.engine === 'whisper' && !server?.ready && !loading && (
          <p className="text-[10px] leading-relaxed text-amber-300/80">
            Whisper is selected but no endpoint is ready. Add an OpenAI or Groq key in Settings › AI,
            choose a custom endpoint above, or switch to Browser recognition.
          </p>
        )}
      </SubSection>
    </Panel>
  );
}

export default VoiceInputSettings;
