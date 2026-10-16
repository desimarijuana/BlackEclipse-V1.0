// ── GhostAvatar ──────────────────────────────────────────────────────────────
// Renders a bot's ghost face as a self-contained SVG. Pure and deterministic:
// the same `GhostSpec` always draws the same character, at any size, in both
// themes (features use a fixed ink color; the body/accent carry the identity).
//
// Kept dependency-free and inline so it works anywhere — cards, list rows,
// dialogs, the customizer preview — without an image request.

'use client';

import { useId, useMemo } from 'react';
import { cn } from '@/lib/utils';
import {
  GHOST_VARIANT_COUNT,
  type GhostSpec,
} from '@/lib/bots/ghost';
import type { GhostMood } from '@/lib/bots/ghost-mood';

const INK = '#241f31';

// Eye styles that already read as closed — the live avatar must not animate a
// blink on them (it would look like a glitch, not a blink).
const CLOSED_EYES = new Set([2, 4]);

interface BodyParams {
  l: number;
  r: number;
  top: number;
  bot: number;
  waves: number;
}

const BODIES: readonly BodyParams[] = [
  { l: 24, r: 96, top: 22, bot: 104, waves: 3 }, // classic
  { l: 16, r: 104, top: 28, bot: 100, waves: 2 }, // wide
  { l: 26, r: 94, top: 16, bot: 106, waves: 4 }, // tall
  { l: 30, r: 90, top: 24, bot: 102, waves: 3 }, // slim
];

function bodyPath(variant: number): string {
  const p = BODIES[Math.max(0, Math.min(GHOST_VARIANT_COUNT - 1, variant))];
  const radius = Math.min((p.r - p.l) / 2, 30);
  let d =
    `M ${p.l} ${p.bot} L ${p.l} ${p.top + radius} ` +
    `Q ${p.l} ${p.top} ${p.l + radius} ${p.top} ` +
    `L ${p.r - radius} ${p.top} ` +
    `Q ${p.r} ${p.top} ${p.r} ${p.top + radius} ` +
    `L ${p.r} ${p.bot}`;
  const seg = (p.r - p.l) / p.waves;
  for (let i = 0; i < p.waves; i += 1) {
    const x1 = p.r - i * seg;
    const x2 = p.r - (i + 1) * seg;
    d += ` Q ${(x1 + x2) / 2} ${p.bot + 11} ${x2} ${p.bot}`;
  }
  return `${d} Z`;
}

function Eyes({ style, accent }: { style: number; accent: string }) {
  const left = 44;
  const right = 76;
  const cy = 52;
  switch (style) {
    case 1: // wide ovals with a highlight
      return (
        <g>
          <ellipse cx={left} cy={cy} rx={7} ry={9} fill={INK} />
          <ellipse cx={right} cy={cy} rx={7} ry={9} fill={INK} />
          <circle cx={left + 2.4} cy={cy - 3} r={2} fill="#ffffff" opacity={0.9} />
          <circle cx={right + 2.4} cy={cy - 3} r={2} fill="#ffffff" opacity={0.9} />
        </g>
      );
    case 2: // happy closed eyes ^ ^
      return (
        <g fill="none" stroke={INK} strokeWidth={3.4} strokeLinecap="round">
          <path d={`M ${left - 6} ${cy + 3} Q ${left} ${cy - 6} ${left + 6} ${cy + 3}`} />
          <path d={`M ${right - 6} ${cy + 3} Q ${right} ${cy - 6} ${right + 6} ${cy + 3}`} />
        </g>
      );
    case 3: // star eyes
      return (
        <g fill={INK}>
          {[left, right].map((cx) => (
            <path
              key={cx}
              transform={`translate(${cx} ${cy})`}
              d="M 0 -8 L 2.2 -2.4 L 8 -2.4 L 3.4 1.2 L 5.2 7 L 0 3.2 L -5.2 7 L -3.4 1.2 L -8 -2.4 L -2.2 -2.4 Z"
            />
          ))}
        </g>
      );
    case 4: // sleepy lines
      return (
        <g stroke={INK} strokeWidth={3.4} strokeLinecap="round">
          <line x1={left - 7} y1={cy} x2={left + 7} y2={cy} />
          <line x1={right - 7} y1={cy} x2={right + 7} y2={cy} />
        </g>
      );
    case 5: // accent plus-sparkle eyes
      return (
        <g stroke={accent} strokeWidth={3.6} strokeLinecap="round">
          <line x1={left} y1={cy - 7} x2={left} y2={cy + 7} />
          <line x1={left - 7} y1={cy} x2={left + 7} y2={cy} />
          <line x1={right} y1={cy - 7} x2={right} y2={cy + 7} />
          <line x1={right - 7} y1={cy} x2={right + 7} y2={cy} />
        </g>
      );
    default: // round beads
      return (
        <g fill={INK}>
          <circle cx={left} cy={cy} r={6} />
          <circle cx={right} cy={cy} r={6} />
        </g>
      );
  }
}

function Mouth({ style }: { style: number }) {
  const cy = 70;
  switch (style) {
    case 1: // open smile
      return <path d={`M 52 ${cy} Q 60 ${cy + 12} 68 ${cy} Z`} fill={INK} />;
    case 2: // flat
      return <line x1={52} y1={cy + 2} x2={68} y2={cy + 2} stroke={INK} strokeWidth={3.4} strokeLinecap="round" />;
    case 3: // small o
      return <circle cx={60} cy={cy + 2} r={3.4} fill={INK} />;
    case 4: // wide grin
      return (
        <g>
          <path d={`M 50 ${cy - 1} Q 60 ${cy + 13} 70 ${cy - 1}`} fill="none" stroke={INK} strokeWidth={3.2} strokeLinecap="round" />
          <line x1={55} y1={cy + 1.5} x2={55} y2={cy + 6} stroke={INK} strokeWidth={1.6} />
          <line x1={60} y1={cy + 2.5} x2={60} y2={cy + 8} stroke={INK} strokeWidth={1.6} />
          <line x1={65} y1={cy + 1.5} x2={65} y2={cy + 6} stroke={INK} strokeWidth={1.6} />
        </g>
      );
    default: // gentle smile
      return <path d={`M 53 ${cy} Q 60 ${cy + 8} 67 ${cy}`} fill="none" stroke={INK} strokeWidth={3.2} strokeLinecap="round" />;
  }
}

function Accessory({ style, accent }: { style: number; accent: string }) {
  switch (style) {
    case 1: // antenna
      return (
        <g>
          <line x1={60} y1={22} x2={60} y2={10} stroke={accent} strokeWidth={3} strokeLinecap="round" />
          <circle cx={60} cy={8} r={4.4} fill={accent} />
        </g>
      );
    case 2: // party hat
      return (
        <g>
          <path d="M 48 26 L 60 4 L 72 26 Z" fill={accent} />
          <circle cx={60} cy={4} r={3.4} fill="#ffffff" opacity={0.85} />
        </g>
      );
    case 3: // halo
      return <ellipse cx={60} cy={12} rx={16} ry={4.5} fill="none" stroke={accent} strokeWidth={3.4} />;
    case 4: // horns
      return (
        <g fill={accent}>
          <path d="M 36 26 L 40 10 L 48 24 Z" />
          <path d="M 84 26 L 80 10 L 72 24 Z" />
        </g>
      );
    case 5: // headphones
      return (
        <g>
          <path d="M 30 52 Q 60 6 90 52" fill="none" stroke={accent} strokeWidth={4.4} strokeLinecap="round" />
          <rect x={24} y={44} width={11} height={17} rx={5} fill={accent} />
          <rect x={85} y={44} width={11} height={17} rx={5} fill={accent} />
        </g>
      );
    case 6: // crown
      return (
        <path
          d="M 42 24 L 46 9 L 54 20 L 60 6 L 66 20 L 74 9 L 78 24 Z"
          fill={accent}
        />
      );
    default:
      return null;
  }
}

function Pattern({ style, accent }: { style: number; accent: string }) {
  switch (style) {
    case 1: // polka dots
      return (
        <g fill={accent} opacity={0.55}>
          {[34, 52, 70, 88].map((x) =>
            [70, 88].map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r={2.6} />),
          )}
          <circle cx={43} cy={79} r={2.6} />
          <circle cx={61} cy={79} r={2.6} />
          <circle cx={79} cy={79} r={2.6} />
        </g>
      );
    case 2: // horizontal stripes
      return (
        <g stroke={accent} strokeWidth={4} opacity={0.4}>
          <line x1={20} y1={76} x2={100} y2={76} />
          <line x1={20} y1={88} x2={100} y2={88} />
        </g>
      );
    case 3: // sparkles
      return (
        <g fill={accent} opacity={0.6}>
          {[
            { x: 40, y: 80 },
            { x: 60, y: 90 },
            { x: 80, y: 78 },
          ].map(({ x, y }) => (
            <path
              key={`${x}-${y}`}
              transform={`translate(${x} ${y}) scale(0.5)`}
              d="M 0 -8 L 2.2 -2.4 L 8 -2.4 L 3.4 1.2 L 5.2 7 L 0 3.2 L -5.2 7 L -3.4 1.2 L -8 -2.4 L -2.2 -2.4 Z"
            />
          ))}
        </g>
      );
    default:
      return null;
  }
}

export interface GhostAvatarProps {
  spec: GhostSpec;
  /** Rendered pixel size (square). Defaults to 48. */
  size?: number;
  className?: string;
  /** Accessible label; when set the SVG exposes an image role. */
  title?: string;
  /** Face expression the live wrapper animates. Absent = no mood attribute. */
  mood?: GhostMood;
}

export function GhostAvatar({ spec, size = 48, className, title, mood }: GhostAvatarProps) {
  // A unique, DOM-safe clip id per instance so multiple ghosts on the same page
  // never collide (duplicate ids are invalid and resolve unpredictably).
  const rawId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const clipId = useMemo(() => `ghost-clip-${rawId}`, [rawId]);
  const path = useMemo(() => bodyPath(spec.variant), [spec.variant]);

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      className={cn('be-ghost shrink-0 select-none', className)}
      role={title ? 'img' : 'presentation'}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      {...(CLOSED_EYES.has(spec.eyes) ? { 'data-eyes-closed': '' } : {})}
      {...(mood && mood !== 'idle' ? { 'data-mood': mood } : {})}
    >
      <defs>
        <clipPath id={clipId}>
          <path d={path} />
        </clipPath>
      </defs>
      <g className="be-ghost__body">
        <path d={path} fill={spec.bodyColor} />
        <g clipPath={`url(#${clipId})`}>
          <Pattern style={spec.pattern} accent={spec.accentColor} />
        </g>
        <Accessory style={spec.accessory} accent={spec.accentColor} />
      </g>
      <g className="be-ghost__gaze">
        <g className="be-ghost__eyes">
          <Eyes style={spec.eyes} accent={spec.accentColor} />
        </g>
      </g>
      <g className="be-ghost__mouth">
        <Mouth style={spec.mouth} />
      </g>
    </svg>
  );
}
