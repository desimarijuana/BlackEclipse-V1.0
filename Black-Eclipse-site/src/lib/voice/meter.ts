// ── Microphone meter ────────────────────────────────────────────────────────
// The voice field needs two numbers while the operator speaks: how LOUD (drives
// flame height and spark rate) and how BRIGHT (spectral centroid, drives colour
// temperature). Both come from an AnalyserNode attached to the SAME stream the
// recorder already owns — nothing extra is captured, and the graph is never
// connected to the speakers (no monitoring, no feedback).
//
// The maths is pure and exported so it can be tested without a browser.

export interface MeterReading {
  /** 0..1, smoothed loudness. */
  level: number;
  /** 0..1, smoothed spectral centroid (bright speech burns hotter). */
  centroid: number;
}

/** Root-mean-square of an 8-bit time-domain buffer (128 = silence). */
export function rmsFromTimeDomain(data: Uint8Array): number {
  if (data.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < data.length; i += 1) {
    const v = (data[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / data.length);
}

/**
 * Map raw RMS to a usable 0..1 drive.
 *
 * Speech sits far below full scale: a comfortable voice is ~0.02–0.12 RMS, so a
 * linear mapping would leave the flame dead. Subtract a noise floor, apply a
 * gentle gamma to lift quiet syllables, and clamp. Never returns NaN.
 */
export function rmsToLevel(rms: number, floor = 0.008): number {
  if (!Number.isFinite(rms) || rms <= floor) return 0;
  const lifted = Math.min(1, (rms - floor) / 0.22);
  return Math.min(1, Math.pow(lifted, 0.65));
}

/** Asymmetric smoothing: sparks jump on attack, embers fade slowly. */
export function smoothLevel(prev: number, next: number, attack = 0.5, release = 0.12): number {
  const a = next > prev ? attack : release;
  const out = prev + (next - prev) * a;
  return Number.isFinite(out) ? Math.min(1, Math.max(0, out)) : prev;
}

/**
 * Normalised spectral centroid (0..1) from an FFT magnitude buffer.
 * A low rumble sits near 0; sibilance and bright speech climb toward 1.
 */
export function spectralCentroid(freq: Uint8Array, sampleRate: number): number {
  if (freq.length === 0 || !Number.isFinite(sampleRate) || sampleRate <= 0) return 0;
  let weighted = 0;
  let total = 0;
  for (let i = 0; i < freq.length; i += 1) {
    const m = freq[i];
    if (m === 0) continue;
    weighted += (i / freq.length) * m;
    total += m;
  }
  if (total === 0) return 0;
  const centre = weighted / total;
  const value = centre * 2.6; // speech centroids cluster low; stretch the range
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
}

interface AudioGraph {
  ctx: AudioContext;
  source: MediaStreamAudioSourceNode;
  analyser: AnalyserNode;
}

/** Live meter over an existing MediaStream. Call `close()` on stop/cancel. */
export class VoiceMeter {
  private graph: AudioGraph | null = null;
  private time: Uint8Array<ArrayBuffer> | null = null;
  private freq: Uint8Array<ArrayBuffer> | null = null;
  private level = 0;
  private centroid = 0;
  private closed = false;

  /** Throws when Web Audio or the stream is unavailable; callers must degrade. */
  constructor(stream: MediaStream) {
    const w = window as unknown as {
      AudioContext?: typeof AudioContext;
      webkitAudioContext?: typeof AudioContext;
    };
    const Ctx = w.AudioContext ?? w.webkitAudioContext;
    if (!Ctx || !stream.active) throw new Error('Audio metering is not available');

    const ctx = new Ctx();
    // A user gesture opened the microphone; resume is still required by some
    // engines after the context is created outside a click handler chain.
    if (ctx.state === 'suspended') void ctx.resume().catch(() => undefined);

    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.55;

    source.connect(analyser);
    // Intentionally NOT connected to ctx.destination.

    this.graph = { ctx, source, analyser };
    this.time = new Uint8Array(analyser.fftSize);
    this.freq = new Uint8Array(analyser.frequencyBinCount);
  }

  /** Latest smoothed reading. Safe to call at any rate; cheap. */
  read(): MeterReading {
    const { analyser, ctx } = this.graph ?? {};
    if (!analyser || !ctx || !this.time || !this.freq || this.closed) {
      return { level: this.level, centroid: this.centroid };
    }

    analyser.getByteTimeDomainData(this.time);
    this.level = smoothLevel(this.level, rmsToLevel(rmsFromTimeDomain(this.time)));

    analyser.getByteFrequencyData(this.freq);
    this.centroid = smoothLevel(this.centroid, spectralCentroid(this.freq, ctx.sampleRate), 0.35, 0.08);

    return { level: this.level, centroid: this.centroid };
  }

  /** Tear down the graph. Never touches the stream's tracks. */
  close(): void {
    if (this.closed) return;
    this.closed = true;
    const graph = this.graph;
    this.graph = null;
    this.time = null;
    this.freq = null;
    if (!graph) return;
    try {
      graph.source.disconnect();
      graph.analyser.disconnect();
    } catch {
      /* already detached */
    }
    void graph.ctx.close().catch(() => undefined);
  }
}
