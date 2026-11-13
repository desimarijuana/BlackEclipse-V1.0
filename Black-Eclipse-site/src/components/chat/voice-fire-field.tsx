'use client';

// ── Voice fire field ────────────────────────────────────────────────────────
// The canvas host for `fire-field.ts`. It owns exactly one rAF loop, reads the
// microphone meter through a ref (never React state) and paints:
//   1. a soft coal-bed glow,
//   2. the heat grid upscaled from a tiny offscreen bitmap,
//   3. additive embers,
//   4. the transcript as real DOM text (aria-live), not canvas glyphs.
//
// Reduced motion / animations-off gets ONE static ember frame — no loop.

import { useEffect, useRef, useState } from 'react';
import { heatAlpha, heatColor, createFireField, stepFire, type FireField } from '@/lib/voice/fire-field';
import type { VoiceMeter } from '@/lib/voice/meter';
import { cn } from '@/lib/utils';

export type VoiceFirePhase = 'starting' | 'recording' | 'transcribing';

export interface VoiceFireFieldProps {
  meterRef: React.RefObject<VoiceMeter | null>;
  phase: VoiceFirePhase;
  /** Committed words (browser dictation); empty for the Whisper path. */
  transcript?: string;
  /** The unconfirmed tail of a browser transcript. */
  interim?: string;
  className?: string;
  height?: number;
}

const DPR_CAP = 2;
const IDLE_LABEL = 'Listening — speak naturally';
const TRANSCRIBING_LABEL = 'Transcribing…';

export function VoiceFireField({
  meterRef,
  phase,
  transcript = '',
  interim = '',
  className,
  height = 84,
}: VoiceFireFieldProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fieldRef = useRef<FireField | null>(null);
  const pointerRef = useRef<{ x: number | null; y: number | null }>({ x: null, y: null });
  const flareRef = useRef(0);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => {
      const root = document.documentElement;
      setReduced(
        mq.matches ||
          root.classList.contains('a11y-reduce-motion') ||
          root.classList.contains('theme-no-anim') ||
          root.classList.contains('motion-off'),
      );
    };
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = hostRef.current;
    if (!canvas || !host) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const off = document.createElement('canvas');
    const offCtx = off.getContext('2d');
    let image: ImageData | null = null;
    let raf = 0;
    let ignition = 0;
    let size = { w: 1, h: 1 };
    let disposed = false;

    const resize = () => {
      const rect = host.getBoundingClientRect();
      const dpr = Math.min(DPR_CAP, window.devicePixelRatio || 1);
      const width = Math.max(1, Math.floor(rect.width));
      const cssHeight = Math.max(1, Math.floor(rect.height || height));
      size = { w: width, h: cssHeight };
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(cssHeight * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${cssHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const cols = Math.min(140, Math.max(28, Math.round(width / 7)));
      const rows = Math.min(52, Math.max(12, Math.round(cssHeight / 6)));
      const current = fieldRef.current;
      if (!current || current.cols !== cols || current.rows !== rows) {
        fieldRef.current = createFireField({ cols, rows, maxEmbers: Math.round(Math.min(140, Math.max(36, (width * cssHeight) / 1400))) });
        off.width = cols;
        off.height = rows;
        image = offCtx ? offCtx.createImageData(cols, rows) : null;
      }
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);

    const draw = (dt: number) => {
      const field = fieldRef.current;
      if (!field || !image) return;
      const width = size.w;
      const cssHeight = size.h;
      const reading = meterRef.current?.read() ?? { level: 0, centroid: 0.3 };
      const phaseNow = phaseRef.current;

      // Ignition ramps the flame in; transcribing banks it down.
      ignition = phaseNow === 'starting' ? Math.min(1, ignition + dt * 2.2) : 1;
      const target = phaseNow === 'transcribing' ? 0.16 : 1;
      const level = reading.level * ignition * target;
      const centroid = phaseNow === 'transcribing' ? 0.1 : reading.centroid;

      stepFire(field, dt, {
        level,
        centroid,
        pointerX: pointerRef.current.x,
        pointerY: pointerRef.current.y,
        flare: flareRef.current,
      });
      flareRef.current = Math.max(0, flareRef.current - dt * 2.4);

      ctx.clearRect(0, 0, width, cssHeight);

      // 1. Coal-bed glow.
      const energy = field.energy;
      const glowY = cssHeight - 2;
      const glowR = Math.max(width * 0.35, 60) * (0.55 + energy * 0.65);
      const glow = ctx.createRadialGradient(width / 2, glowY, 0, width / 2, glowY, glowR);
      const [gr, gg, gb] = heatColor(0.55 + energy * 0.3, centroid);
      glow.addColorStop(0, `rgba(${gr}, ${gg}, ${gb}, ${0.16 + energy * 0.24})`);
      glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, width, cssHeight);

      // 2. Heat grid → a cols × rows bitmap → one smoothed drawImage.
      const data = image.data;
      for (let y = 0; y < field.rows; y += 1) {
        const srcRow = (field.rows - 1 - y) * field.cols; // flip: row 0 is the bed
        const dstRow = y * field.cols * 4;
        for (let x = 0; x < field.cols; x += 1) {
          const v = field.heat[srcRow + x];
          const i = dstRow + x * 4;
          if (v < 0.02) {
            data[i + 3] = 0;
            continue;
          }
          const [r, g, b] = heatColor(v, centroid);
          data[i] = r;
          data[i + 1] = g;
          data[i + 2] = b;
          data[i + 3] = Math.round(heatAlpha(v) * 255);
        }
      }
      offCtx?.putImageData(image, 0, 0);
      ctx.globalCompositeOperation = 'lighter';
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(off, 0, 0, width, cssHeight);
      ctx.globalCompositeOperation = 'source-over';

      // 3. Embers.
      ctx.globalCompositeOperation = 'lighter';
      for (const ember of field.embers) {
        if (!ember.alive) continue;
        const px = (ember.x / field.cols) * width;
        const py = cssHeight - (ember.y / field.rows) * cssHeight;
        const life = Math.max(0, ember.life / ember.maxLife);
        const [er, eg, eb] = heatColor(0.55 + ember.heat * 0.45, centroid);
        ctx.fillStyle = `rgba(${er}, ${eg}, ${eb}, ${life * 0.9})`;
        const size = life > 0.65 ? 2 : 1.4;
        ctx.fillRect(px - size / 2, py - size / 2, size, size);
      }
      ctx.globalCompositeOperation = 'source-over';
    };

    let prevT = 0;
    const frameMs = 1000 / 30;
    const loop = (t: number) => {
      if (disposed) return;
      if (prevT !== 0 && t - prevT < frameMs) {
        raf = requestAnimationFrame(loop);
        return;
      }
      const dt = prevT === 0 ? 0.016 : Math.min(0.06, (t - prevT) / 1000);
      prevT = t;
      if (!document.hidden) draw(dt);
      raf = requestAnimationFrame(loop);
    };

    if (!reduced) {
      raf = requestAnimationFrame(loop);
    } else {
      // One static frame: a low, warm ember bed. No motion, no particles.
      draw(0.016);
    }

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      fieldRef.current = null;
    };
  }, [height, meterRef, reduced]);

  const text = `${transcript}${transcript && interim ? ' ' : ''}${interim}`;

  return (
    <div
      ref={hostRef}
      className={cn('relative w-full select-none overflow-hidden rounded-2xl', className)}
      style={{ height }}
    >
      <canvas ref={canvasRef} aria-hidden className="absolute inset-0 block h-full w-full" />
      <div className="pointer-events-none absolute inset-x-0 top-0 flex h-full flex-col justify-center px-3">
        <p
          role="status"
          aria-live="polite"
          aria-atomic="false"
          className="max-h-[3.2em] overflow-hidden text-center font-mono text-[12px] leading-relaxed text-foreground/90"
        >
          {phase === 'transcribing' ? (
            <span className="text-muted-foreground">{TRANSCRIBING_LABEL}</span>
          ) : text ? (
            <>
              <span className="text-foreground">{transcript}</span>
              {interim && <span className="text-foreground/45"> {interim}</span>}
              <span className="ml-0.5 inline-block w-[0.5em] animate-pulse text-primary" aria-hidden>
                ▌
              </span>
            </>
          ) : (
            <span className="text-muted-foreground/70">{IDLE_LABEL}</span>
          )}
        </p>
      </div>

      {/* Pointer wind / tap flare. Touch drag works the same way. */}
      <div
        aria-hidden
        className="absolute inset-0"
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          pointerRef.current = {
            x: (e.clientX - rect.left) / rect.width,
            y: (e.clientY - rect.top) / rect.height,
          };
        }}
        onPointerLeave={() => {
          pointerRef.current = { x: null, y: null };
        }}
        onPointerDown={(e) => {
          flareRef.current = 1;
          const rect = e.currentTarget.getBoundingClientRect();
          pointerRef.current = {
            x: (e.clientX - rect.left) / rect.width,
            y: (e.clientY - rect.top) / rect.height,
          };
        }}
      />
    </div>
  );
}

export default VoiceFireField;
