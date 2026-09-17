'use client';

// ── Investor Eye — Animated starfield ────────────────────────────────────────
// The globe is the hero, so it needs living space behind it. A static dot field
// reads as wallpaper; the surface should feel like a live star chart.
//
// What animates, and why each thing earns its CPU:
//   - PARALLAX DRIFT: three star layers move at different speeds, so dragging the
//     globe past them creates real depth (the classic cue that the background is
//     far away). One shared "camera" offset drives all of them.
//   - TWINKLE: only the near tier breathes, via a per-star phase. Twinkling the
//     far tier would make the whole sky shimmer and read as noise.
//   - SHOOTING STARS: frequent meteors with a fading tail. They are the thing
//     that makes a night sky feel alive, and they cost almost nothing because at
//     most three exist at once. The first spawns almost immediately — a meteor
//     that only appears after ten seconds reads as "the background is static".
//
// TWO SKINS, matching the map surface (`MapSkin`):
//   - `glow`  the living sky described above,
//   - `black` the first-draft still sky: flat black, fixed stars, no meteors.
//     A motionless background is the POINT of the plain terminal skin, so the
//     loop is skipped entirely there and one frame is painted.
//
// Budget discipline (this screen also runs an ECharts GL render loop):
//   - one canvas, one rAF loop, real elapsed time (never an assumed 60fps, so
//     the drift and the meteors run at the same speed on a 120Hz display),
//   - no per-frame allocation of gradients for stars (halos are pre-rendered
//     into sprites ONCE and blitted with drawImage),
//   - capped DPR, and the loop fully stops when the tab is hidden,
//   - `prefers-reduced-motion` renders a single static frame and never starts
//     the loop,
//   - pointer-events-none so it can never eat a map drag or a pin click.

import { useEffect, useRef } from 'react';

interface StarfieldProps {
  className?: string;
  /** Star density multiplier. Smaller canvases want fewer stars. */
  density?: number;
  /**
   * `glow` is the living sky: blue nebula, parallax drift, twinkle and frequent
   * shooting stars. `black` is the first-draft still sky — a flat black field
   * with a fixed star field and no meteors, matching the plain terminal skin.
   */
  skin?: 'black' | 'glow';
}

/** Deterministic xorshift32 — the sky is identical every mount (a reshuffling
 *  sky looks broken), while the animation makes it feel alive. */
function makeRandom(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13; s |= 0;
    s ^= s >>> 17;
    s ^= s << 5; s |= 0;
    return ((s >>> 0) % 100000) / 100000;
  };
}

interface Star {
  x: number;
  y: number;
  r: number;
  a: number;
  /** Parallax depth: 0 far … 1 near. Drives drift speed and twinkle. */
  depth: number;
  /** Twinkle phase offset, so stars do not pulse in unison. */
  phase: number;
  /** Twinkle speed. */
  speed: number;
}

interface Meteor {
  x: number;
  y: number;
  vx: number;
  vy: number;
  len: number;
  life: number;
  maxLife: number;
}

/**
 * Pre-render a soft radial glow into a small offscreen canvas. Blitting this is
 * far cheaper than building a `createRadialGradient` per star per frame, which
 * is what would otherwise make an animated field unaffordable.
 */
function makeGlowSprite(size: number, color: string): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  const ctx = c.getContext('2d');
  if (ctx) {
    const r = size / 2;
    const g = ctx.createRadialGradient(r, r, 0, r, r, r);
    g.addColorStop(0, color);
    g.addColorStop(0.35, color.replace(/[\d.]+\)$/, '0.35)'));
    g.addColorStop(1, color.replace(/[\d.]+\)$/, '0)'));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
  }
  return c;
}

export function Starfield({ className, density = 1, skin = 'glow' }: StarfieldProps) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent) return;

    const isGlow = skin === 'glow';
    const reduceMotion = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // `black` is the still sky: one frame, no meteors, no drift.
    const animate = isGlow && !reduceMotion;

    const glowWhite = makeGlowSprite(64, 'rgba(240,249,255,1)');
    const glowCyan = makeGlowSprite(64, 'rgba(125,211,252,0.9)');

    let stars: Star[] = [];
    let meteors: Meteor[] = [];
    let w = 0;
    let h = 0;
    let raf = 0;
    let running = true;
    // First meteor is nearly immediate, so "alive" is visible on arrival.
    let meteorTimer = 0.6;
    let lastTs = 0;

    const buildStars = () => {
      const rand = makeRandom(0x9e3779b9);
      const count = Math.floor(((w * h) / 2400) * density);
      stars = [];
      for (let i = 0; i < count; i++) {
        const tier = rand();
        // Three depth tiers. The near tier is rarer, bigger and brighter.
        const depth = tier > 0.97 ? 0.85 + rand() * 0.15
          : tier > 0.85 ? 0.45 + rand() * 0.25
            : 0.05 + rand() * 0.3;
        stars.push({
          x: rand() * w,
          y: rand() * h,
          r: depth > 0.8 ? 1.2 + rand() * 1.1 : depth > 0.4 ? 0.8 + rand() * 0.6 : 0.5 + rand() * 0.4,
          a: depth > 0.8 ? 0.75 + rand() * 0.25 : depth > 0.4 ? 0.35 + rand() * 0.35 : 0.12 + rand() * 0.3,
          depth,
          phase: rand() * Math.PI * 2,
          speed: 0.4 + rand() * 1.1,
        });
      }
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = parent.clientWidth;
      h = parent.clientHeight;
      if (w === 0 || h === 0) return;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildStars();
    };

    /** Wrap a drifting coordinate back into the viewport. */
    const wrap = (v: number, span: number) => ((v % span) + span) % span;

    const drawFrame = (tSec: number, dt: number) => {
      const ctx = canvas.getContext('2d');
      if (!ctx || w === 0 || h === 0) return;
      ctx.clearRect(0, 0, w, h);

      // ── Base sky ──────────────────────────────────────────────────────────
      const sky = ctx.createLinearGradient(0, 0, 0, h);
      if (isGlow) {
        // Deep blue rather than black, so the sky belongs to the same blue
        // planet as the surface. Still dark enough to let the pins read.
        sky.addColorStop(0, '#04102b');
        sky.addColorStop(0.55, '#071a3d');
        sky.addColorStop(1, '#04102b');
      } else {
        sky.addColorStop(0, '#030303');
        sky.addColorStop(0.55, '#060607');
        sky.addColorStop(1, '#030303');
      }
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, w, h);

      // ── Nebula wash: slow-drifting, very low alpha ────────────────────────
      // The drift is deliberately glacial (~40s per cycle) so it registers as
      // atmosphere rather than motion competing with the globe. The plain skin
      // paints its nebula at a fixed phase, so the sky is completely still.
      const nebT = isGlow ? tSec : 4;
      const nx = Math.sin((nebT / 40) * Math.PI * 2) * w * 0.04;
      const ny = Math.cos((nebT / 55) * Math.PI * 2) * h * 0.03;
      const nebula = (cx: number, cy: number, r: number, color: string) => {
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        g.addColorStop(0, color);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, h);
      };
      if (isGlow) {
        nebula(w * 0.28 + nx, h * 0.32 + ny, Math.max(w, h) * 0.45, 'rgba(37,99,235,0.20)');
        nebula(w * 0.76 - nx, h * 0.72 - ny, Math.max(w, h) * 0.42, 'rgba(129,140,248,0.14)');
      } else {
        nebula(w * 0.28, h * 0.32, Math.max(w, h) * 0.45, 'rgba(255,255,255,0.02)');
      }

      // ── Stars: parallax drift + near-tier twinkle ─────────────────────────
      // One "camera" offset per depth tier. Near tiers travel further, which is
      // the whole parallax effect.
      const drift = tSec * 2.6;
      for (const s of stars) {
        const dx = wrap(s.x + drift * s.depth * 6, w + 40) - 20;
        const dy = wrap(s.y, h + 40) - 20;
        // Twinkle only the near tier — a shimmering far field reads as noise.
        const twinkle = animate && s.depth > 0.8
          ? 0.7 + 0.3 * Math.sin(tSec * s.speed + s.phase)
          : 1;
        const alpha = s.a * twinkle;

        if (s.depth > 0.8) {
          // Bright star: pre-rendered halo sprite + solid core.
          const size = s.r * 12;
          ctx.globalAlpha = alpha * 0.9;
          ctx.drawImage(s.depth > 0.9 ? glowWhite : glowCyan, dx - size / 2, dy - size / 2, size, size);
          ctx.globalAlpha = alpha;
          ctx.fillStyle = '#ffffff';
          ctx.beginPath();
          ctx.arc(dx, dy, s.r, 0, Math.PI * 2);
          ctx.fill();
        } else if (s.depth > 0.4) {
          ctx.globalAlpha = alpha;
          ctx.fillStyle = '#e2e8f0';
          ctx.beginPath();
          ctx.arc(dx, dy, s.r, 0, Math.PI * 2);
          ctx.fill();
        } else {
          ctx.globalAlpha = alpha;
          ctx.fillStyle = '#cbd5e1';
          ctx.fillRect(dx, dy, 1, 1);
        }
      }
      ctx.globalAlpha = 1;

      // ── Shooting stars ────────────────────────────────────────────────────
      if (animate) {
        meteorTimer -= dt;
        // At most three in flight; a sky full of meteors looks like rainfall.
        if (meteorTimer <= 0 && meteors.length < 3) {
          const rand = makeRandom((tSec * 1000) | 0);
          const fromLeft = rand() > 0.5;
          const speed = 240 + rand() * 260;
          const angle = (fromLeft ? 0.32 : Math.PI - 0.32) + (rand() - 0.5) * 0.22;
          meteors.push({
            x: fromLeft ? -40 : w + 40,
            y: rand() * h * 0.55,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            len: 90 + rand() * 130,
            life: 0,
            maxLife: 1.1 + rand() * 0.7,
          });
          // Regular, but never metronomic: a meteor every 3–8s keeps the sky
          // alive without turning it into a fireworks display.
          meteorTimer = 3 + rand() * 5;
        }
      }

      meteors = meteors.filter((m) => {
        m.life += dt;
        m.x += m.vx * dt;
        m.y += m.vy * dt;
        const p = m.life / m.maxLife;
        if (p >= 1) return false;
        // Fade in fast, out slow — a meteor appears abruptly and trails off.
        const alpha = p < 0.12 ? p / 0.12 : 1 - (p - 0.12) / 0.88;
        const mag = Math.hypot(m.vx, m.vy);
        const tx = m.x - (m.vx / mag) * m.len;
        const ty = m.y - (m.vy / mag) * m.len;
        const grad = ctx.createLinearGradient(m.x, m.y, tx, ty);
        grad.addColorStop(0, `rgba(255,255,255,${0.9 * alpha})`);
        grad.addColorStop(0.35, `rgba(186,230,253,${0.45 * alpha})`);
        grad.addColorStop(1, 'rgba(186,230,253,0)');
        ctx.strokeStyle = grad;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(m.x, m.y);
        ctx.lineTo(tx, ty);
        ctx.stroke();
        // A bright head, so the streak reads as a moving object.
        const head = ctx.createRadialGradient(m.x, m.y, 0, m.x, m.y, 9);
        head.addColorStop(0, `rgba(255,255,255,${alpha})`);
        head.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = head;
        ctx.fillRect(m.x - 9, m.y - 9, 18, 18);
        return true;
      });
    };

    const start = performance.now();
    const loop = (now: number) => {
      if (!running) return;
      // Real elapsed time, clamped so a backgrounded tab (where rAF pauses and
      // the delta becomes huge) never teleports stars or stretches a meteor
      // across the whole sky when it resumes.
      const dt = lastTs ? Math.min(0.05, (now - lastTs) / 1000) : 1 / 60;
      lastTs = now;
      drawFrame((now - start) / 1000, dt);
      raf = requestAnimationFrame(loop);
    };

    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (animate) {
        running = true;
        lastTs = 0;
        raf = requestAnimationFrame(loop);
      }
    };

    resize();
    if (animate) {
      raf = requestAnimationFrame(loop);
    } else {
      // One still frame — the plain skin, and a reduced-motion preference, both
      // opt out of an animated sky. A fixed time gives the identical star field
      // every mount.
      drawFrame(4, 1 / 60);
    }

    const ro = new ResizeObserver(() => {
      resize();
      if (!animate) drawFrame(4, 1 / 60);
    });
    ro.observe(parent);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [density, skin]);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className={className}
      style={{ display: 'block', pointerEvents: 'none' }}
    />
  );
}
