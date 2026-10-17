// ── Model3dFallback — a static isometric wireframe ────────────────────────────
//
// When WebGL is unavailable (or the context is lost) the figure must not be a
// blank rectangle. This draws the compiled scene's feature edges as an isometric
// SVG using the SAME outline palette (#3A3E44 on the paper), plus the numbered
// hotspots — a readable, deterministic fallback with no GPU.

import { fitProjection, iso, type Point3 } from '@/lib/anatomy/iso-kit';
import type { CompiledModel3d } from '@/lib/model3d/compile';

export interface Model3dFallbackProps {
  scene: CompiledModel3d;
  height: number;
}

export function Model3dFallback({ scene, height }: Model3dFallbackProps) {
  const points: Point3[] = [];
  for (const part of scene.parts) {
    const edges = part.edges;
    for (let i = 0; i < edges.length; i += 3) {
      points.push([edges[i]!, edges[i + 1]!, edges[i + 2]!]);
    }
  }
  if (points.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-[12px] text-white/60">
        No outline to draw.
      </div>
    );
  }

  const projection = fitProjection(points, scene.width, height, {
    pad: 26,
    headroom: 14,
    azimuth: scene.azimuth,
    elevation: scene.elevation,
  });

  const projected = points.map((p) => iso(p, projection));
  const xs = projected.map((p) => p[0]);
  const ys = projected.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const margin = 16;
  const viewBox = `${Math.round(minX - margin)} ${Math.round(minY - margin)} ${Math.round(maxX - minX + margin * 2)} ${Math.round(maxY - minY + margin * 2)}`;

  const path = scene.parts
    .map((part) => {
      const edges = part.edges;
      const segments: string[] = [];
      for (let i = 0; i < edges.length; i += 6) {
        const a = iso([edges[i]!, edges[i + 1]!, edges[i + 2]!], projection);
        const b = iso([edges[i + 3]!, edges[i + 4]!, edges[i + 5]!], projection);
        segments.push(`M${a[0].toFixed(1)} ${a[1].toFixed(1)}L${b[0].toFixed(1)} ${b[1].toFixed(1)}`);
      }
      return segments.join('');
    })
    .join('');

  return (
    <svg
      viewBox={viewBox}
      role="img"
      aria-label={scene.width ? 'Isometric fallback view' : 'Isometric view'}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: 'block', width: '100%', height: '100%' }}
    >
      <path d={path} fill="none" stroke="#3A3E44" strokeWidth={1} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      {scene.keys.map((key, i) => {
        const p = iso([key.anchor[0], key.anchor[1], key.anchor[2]], projection);
        return (
          <g key={key.id}>
            <circle cx={p[0]} cy={p[1]} r={8} fill="#161618" stroke="#6b737c" strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
            <text x={p[0]} y={p[1]} fontSize={10} fontFamily="ui-monospace, monospace" fill="#cfd4d9" textAnchor="middle" dominantBaseline="central">
              {i + 1}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default Model3dFallback;
