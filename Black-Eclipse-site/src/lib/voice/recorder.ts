// ── Audio capture ───────────────────────────────────────────────────────────
// A thin MediaRecorder wrapper for Whisper-style transcription. It records only
// while the operator is holding a dictation open, never persists the audio, and
// always releases the microphone tracks on stop/cancel.

export interface RecordingResult {
  blob: Blob;
  mimeType: string;
  durationMs: number;
}

const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
];

/** The best container this browser can record, or undefined for its default. */
export function pickAudioMimeType(): string | undefined {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') return undefined;
  return MIME_CANDIDATES.find((type) => window.MediaRecorder.isTypeSupported(type));
}

export class VoiceRecorder {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;
  private cancelled = false;
  private resolveStop: ((result: RecordingResult | null) => void) | null = null;

  get active(): boolean {
    return this.recorder !== null;
  }

  /**
   * The live microphone stream, or null between sessions.
   * Exposed so the visual level meter can analyse the SAME stream; it must not
   * take ownership of the tracks (stop/cancel still release them).
   */
  getStream(): MediaStream | null {
    return this.stream;
  }

  async start(): Promise<void> {
    if (this.recorder) return;
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      throw new Error('Recording is not supported in this browser');
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });

    const mimeType = pickAudioMimeType();
    const recorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);

    this.stream = stream;
    this.recorder = recorder;
    this.chunks = [];
    this.cancelled = false;
    this.startedAt = Date.now();

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data);
    };
    recorder.onstop = () => {
      const durationMs = Math.max(0, Date.now() - this.startedAt);
      const type = recorder.mimeType || mimeType || 'audio/webm';
      const blob = this.cancelled ? null : new Blob(this.chunks, { type });
      this.cleanup();
      const resolve = this.resolveStop;
      this.resolveStop = null;
      resolve?.(blob && blob.size > 0 ? { blob, mimeType: type, durationMs } : null);
    };

    recorder.start(250);
  }

  stop(): Promise<RecordingResult | null> {
    return new Promise((resolve) => {
      const recorder = this.recorder;
      if (!recorder || recorder.state === 'inactive') {
        this.cleanup();
        resolve(null);
        return;
      }
      this.resolveStop = resolve;
      try {
        recorder.stop();
      } catch {
        this.cleanup();
        resolve(null);
      }
    });
  }

  /** Abort without producing a result; also used on unmount/navigation. */
  cancel(): void {
    this.cancelled = true;
    const recorder = this.recorder;
    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop();
      } catch {
        this.cleanup();
      }
    } else {
      this.cleanup();
    }
  }

  private cleanup(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
  }
}
