'use client';

// ── Model3dCanvas — the WebGL viewport (charcoal paper + graphite pencil) ─────
//
// Client-only (loaded via next/dynamic ssr:false). Receives an ALREADY COMPILED
// scene — world-space meshes — and does one job: draw it, with explicit,
// scoped camera controls and numbered hotspots.
//
// Controls (all scoped to THIS canvas, never the page):
//  * drag            → orbit
//  * ctrl/cmd-drag   → pan (or right-drag), and full drag mode via the buttons
//  * wheel           → zoom (only while the cursor is over the model)
//  * on-canvas buttons → Orbit / Drag mode, zoom in / out, reset
//
// Robustness (why it no longer goes blank): the <canvas> is created INSIDE the
// effect and removed on teardown, so a StrictMode/re-render remount always gets a
// fresh context and never reuses a lost one; it never calls `WEBGL_lose_context`;
// and it only creates the context once the wrapper reports a non-zero size.

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Camera, Geometry, Mesh, Program, Renderer, Transform, Vec3 } from 'ogl';
import type { CompiledModel3d } from '@/lib/model3d/compile';
import type { Model3dTone } from '@/lib/model3d/names';

const DEG = Math.PI / 180;
const FOV = 35;

// Flat sketch look: the SOLIDS fill with the same colour as the paper
// (#161618) and are read purely by their OUTLINE (#3A3E44). `tone` is reserved
// for the WIRES. Anything drawn at silhouette is the outline colour.
const PAPER: [number, number, number] = [0.086, 0.086, 0.094]; // #161618
const OUTLINE: [number, number, number] = [0.227, 0.243, 0.267]; // #3A3E44
const LIT_OUTLINE: [number, number, number] = [0.55, 0.60, 0.66];

// Wire palette: the shared status vocabulary, desaturated toward coloured pencil.
const TONES: Record<Model3dTone, [number, number, number]> = {
  neutral: [0.74, 0.77, 0.80],
  info: [0.55, 0.68, 0.88],
  success: [0.52, 0.79, 0.62],
  warning: [0.86, 0.73, 0.44],
  danger: [0.87, 0.55, 0.55],
};

const VERTEX = `
attribute vec3 position;
attribute vec3 normal;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
uniform mat3 normalMatrix;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vNormal = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vView = -mv.xyz;
  gl_Position = projectionMatrix * mv;
}`;

const FRAGMENT = `
precision highp float;
uniform vec3 uFill;
uniform vec3 uLine;
uniform float uLit;
uniform float uOpacity;
varying vec3 vNormal;
varying vec3 vView;

void main() {
  vec3 n = normalize(vNormal);
  vec3 v = normalize(vView);
  vec3 fill = mix(uFill, uFill * 1.5, uLit);
  vec3 line = mix(uLine, vec3(0.55, 0.60, 0.66), uLit);
  // Silhouette band: outline only where the surface turns edge-on, so the flat
  // fill never shows and the form reads as a line drawing.
  float f = 1.0 - max(dot(n, v), 0.0);
  float edge = smoothstep(0.55, 0.82, f);
  gl_FragColor = vec4(mix(fill, line, edge), uOpacity);
}`;

const EDGE_VERTEX = `
attribute vec3 position;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
void main() {
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const EDGE_FRAGMENT = `
precision highp float;
uniform vec3 uColor;
uniform float uOpacity;
void main() {
  gl_FragColor = vec4(uColor, uOpacity);
}`;

const LINE_VERTEX = `
attribute vec3 position;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
varying vec3 vPos;
void main() {
  vPos = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const LINE_FRAGMENT = `
precision highp float;
uniform vec3 uColor;
uniform float uOpacity;
uniform float uRange;
varying vec3 vPos;
void main() {
  float d = length(vPos.xy) / uRange;
  if (d > 1.0) discard;
  gl_FragColor = vec4(uColor, (1.0 - d) * uOpacity);
}`;

const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v));

function vec3Of(t: [number, number, number]): Vec3 {
  return new Vec3(t[0], t[1], t[2]);
}

export type Model3dMode = 'orbit' | 'drag';

export interface Model3dCanvasProps {
  scene: CompiledModel3d;
  litGroups: Set<string>;
  still: boolean;
  autoRotate?: boolean;
  onError?: (message: string) => void;
}

function ControlButton({ label, active, onClick, children }: {
  label: string;
  active?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={
        'flex h-7 w-7 items-center justify-center rounded-md border text-[13px] leading-none backdrop-blur-sm transition-colors ' +
        (active
          ? 'border-white/40 bg-white/20 text-white'
          : 'border-white/15 bg-black/45 text-white/70 hover:bg-black/70 hover:text-white')
      }
    >
      {children}
    </button>
  );
}

export function Model3dCanvas({ scene, litGroups, still, autoRotate, onError }: Model3dCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<HTMLDivElement>(null);
  const litRef = useRef(litGroups);
  litRef.current = litGroups;
  const errorRef = useRef(onError);
  errorRef.current = onError;

  const [mode, setMode] = useState<Model3dMode>('orbit');
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const apiRef = useRef<{ zoom: (dir: number) => void; reset: () => void } | null>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;

    let api: { resize: () => void; teardown: () => void } | null = null;

    const start = (): void => {
      const canvas = document.createElement('canvas');
      canvas.style.display = 'block';
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      canvas.style.touchAction = 'none';
      canvas.style.cursor = 'grab';
      wrap.insertBefore(canvas, wrap.firstChild);

      let renderer: Renderer;
      try {
        renderer = new Renderer({
          canvas,
          dpr: Math.min(2, window.devicePixelRatio || 1),
          alpha: true,
          antialias: true,
        });
      } catch {
        canvas.remove();
        errorRef.current?.('WebGL is unavailable in this browser.');
        return;
      }
      const gl = renderer.gl;
      if (!gl) {
        canvas.remove();
        errorRef.current?.('WebGL is unavailable in this browser.');
        return;
      }
      gl.clearColor(0, 0, 0, 0);
      gl.enable(gl.DEPTH_TEST);
      gl.disable(gl.CULL_FACE);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      // Push the flat fills a hair away from the camera so the outline LINES on
      // the surface win the depth test instead of z-fighting with the fill.
      gl.enable(gl.POLYGON_OFFSET_FILL);
      gl.polygonOffset(2.0, 2.0);

      let contextLost = false;
      const onLost = (event: Event) => {
        event.preventDefault();
        contextLost = true;
        errorRef.current?.('The 3D view lost its graphics context. Reopen the figure or use Download .glb.');
      };
      canvas.addEventListener('webglcontextlost', onLost as EventListener);

      const program = new Program(gl, {
        vertex: VERTEX,
        fragment: FRAGMENT,
        uniforms: {
          uFill: { value: PAPER },
          uLine: { value: OUTLINE },
          uLit: { value: 0 },
          uOpacity: { value: 1 },
        },
      });
      const edgeProgram = new Program(gl, {
        vertex: EDGE_VERTEX,
        fragment: EDGE_FRAGMENT,
        uniforms: { uColor: { value: OUTLINE }, uOpacity: { value: 1 } },
      });
      const lineProgram = new Program(gl, {
        vertex: LINE_VERTEX,
        fragment: LINE_FRAGMENT,
        transparent: true,
        depthWrite: false,
        uniforms: { uColor: { value: [0.6, 0.64, 0.68] }, uOpacity: { value: 0.5 }, uRange: { value: 1 } },
      });

      const sceneRoot = new Transform();
      // Compiler is Z-up; keep the whole scene in Y-up for the turntable camera.
      sceneRoot.rotation.x = -Math.PI / 2;

      for (const part of scene.parts) {
        const geometry = new Geometry(gl, {
          position: { size: 3, data: part.mesh.positions },
          normal: { size: 3, data: part.mesh.normals },
          index: { data: part.mesh.indices },
        });
        const alpha = Math.max(0.25, part.opacity);
        const mesh = new Mesh(gl, { geometry, program });
        mesh.onBeforeRender(() => {
          const lit = part.lit || litRef.current.has(part.group);
          program.uniforms.uLit.value = lit ? 1 : 0;
          program.uniforms.uOpacity.value = alpha;
        });
        mesh.setParent(sceneRoot);

        // Outline: the same feature edges as crisp #3A3E44 lines on the surface.
        if (part.edges.length >= 6) {
          const edgeMesh = new Mesh(gl, {
            geometry: new Geometry(gl, { position: { size: 3, data: part.edges } }),
            program: edgeProgram,
            mode: gl.LINES,
          });
          edgeMesh.onBeforeRender(() => {
            const lit = part.lit || litRef.current.has(part.group);
            edgeProgram.uniforms.uColor.value = lit ? LIT_OUTLINE : OUTLINE;
          });
          edgeMesh.setParent(sceneRoot);
        }
      }

      const span =
        Math.max(
          scene.bounds.max[0] - scene.bounds.min[0],
          scene.bounds.max[1] - scene.bounds.min[1],
          40,
        ) * 0.75;
      const gcx = (scene.bounds.min[0] + scene.bounds.max[0]) / 2;
      const gcy = (scene.bounds.min[1] + scene.bounds.max[1]) / 2;
      const gridLines: number[] = [];
      const step = span / 8;
      for (let i = -8; i <= 8; i++) {
        gridLines.push(gcx + i * step, gcy - span, 0, gcx + i * step, gcy + span, 0);
        gridLines.push(gcx - span, gcy + i * step, 0, gcx + span, gcy + i * step, 0);
      }
      const grid = new Mesh(gl, {
        geometry: new Geometry(gl, { position: { size: 3, data: new Float32Array(gridLines) } }),
        program: lineProgram,
        mode: gl.LINES,
      });
      grid.onBeforeRender(() => {
        lineProgram.uniforms.uColor.value = [0.62, 0.66, 0.70];
        lineProgram.uniforms.uOpacity.value = 0.28;
        lineProgram.uniforms.uRange.value = span * 1.45;
      });
      grid.setParent(sceneRoot);

      scene.wires.forEach((wire) => {
        const mesh = new Mesh(gl, {
          geometry: new Geometry(gl, {
            position: { size: 3, data: new Float32Array([...wire.from, ...wire.to]) },
          }),
          program: lineProgram,
          mode: gl.LINES,
        });
        mesh.onBeforeRender(() => {
          lineProgram.uniforms.uColor.value = TONES[wire.tone] ?? TONES.neutral;
          lineProgram.uniforms.uOpacity.value = wire.dotted ? 0.5 : wire.dashed ? 0.65 : 0.95;
          lineProgram.uniforms.uRange.value = 1e9;
        });
        mesh.setParent(sceneRoot);
      });

      // ── Camera + controls (Y-up) ─────────────────────────────────────────
      const camera = new Camera(gl, { fov: FOV, near: 0.1, far: scene.distance * 12 });
      const base = vec3Of([scene.target[0], scene.target[2], -scene.target[1]]);
      let target = new Vec3(base.x, base.y, base.z);
      let radius = scene.distance;
      let theta = scene.azimuth * DEG;
      let phi = scene.elevation * DEG;
      const minRadius = scene.distance * 0.35;
      const maxRadius = scene.distance * 4;

      const applyCamera = () => {
        const cp = Math.cos(phi);
        camera.position.set(
          target.x + radius * cp * Math.sin(theta),
          target.y + radius * Math.sin(phi),
          target.z + radius * cp * Math.cos(theta),
        );
        camera.lookAt(target);
      };
      applyCamera();

      const zoom = (dir: number) => {
        radius = clamp(radius * (dir > 0 ? 0.85 : 1.18), minRadius, maxRadius);
        applyCamera();
      };
      const reset = () => {
        target = new Vec3(base.x, base.y, base.z);
        radius = scene.distance;
        theta = scene.azimuth * DEG;
        phi = scene.elevation * DEG;
        applyCamera();
      };
      apiRef.current = { zoom, reset };

      // ── Pointer: orbit / ctrl(or cmd or right)-drag pan ──────────────────
      let dragging: 'rotate' | 'pan' | null = null;
      let lastX = 0;
      let lastY = 0;
      const onPointerDown = (event: PointerEvent) => {
        if (event.button !== 0 && event.button !== 2) return;
        const pan = event.button === 2 || modeRef.current === 'drag' || event.ctrlKey || event.metaKey;
        dragging = pan ? 'pan' : 'rotate';
        lastX = event.clientX;
        lastY = event.clientY;
        canvas.style.cursor = 'grabbing';
        try { canvas.setPointerCapture(event.pointerId); } catch { /* ignore */ }
        event.preventDefault();
      };
      const onPointerMove = (event: PointerEvent) => {
        if (!dragging) return;
        const dx = event.clientX - lastX;
        const dy = event.clientY - lastY;
        lastX = event.clientX;
        lastY = event.clientY;
        if (dragging === 'rotate') {
          theta -= dx * 0.006;
          phi = clamp(phi + dy * 0.006, -1.45, 1.45);
        } else {
          const scale = (2 * radius * Math.tan((FOV * DEG) / 2)) / Math.max(1, canvas.clientHeight);
          const m = camera.viewMatrix;
          const rx = m[0]!, ry = m[4]!, rz = m[8]!;
          const ux = m[1]!, uy = m[5]!, uz = m[9]!;
          target.set(
            target.x - rx * dx * scale + ux * dy * scale,
            target.y - ry * dx * scale + uy * dy * scale,
            target.z - rz * dx * scale + uz * dy * scale,
          );
        }
        applyCamera();
      };
      const onPointerUp = (event: PointerEvent) => {
        if (!dragging) return;
        dragging = null;
        canvas.style.cursor = 'grab';
        try { canvas.releasePointerCapture(event.pointerId); } catch { /* ignore */ }
      };
      const onContextMenu = (event: Event) => event.preventDefault();
      const onWheel = (event: WheelEvent) => {
        // Zoom only while the cursor is over the model; page scroll is otherwise
        // untouched. Alt is accepted (and not required) for muscle memory.
        event.preventDefault();
        radius = clamp(radius * Math.exp(event.deltaY * 0.0012), minRadius, maxRadius);
        applyCamera();
      };
      canvas.addEventListener('pointerdown', onPointerDown);
      canvas.addEventListener('pointermove', onPointerMove);
      canvas.addEventListener('pointerup', onPointerUp);
      canvas.addEventListener('pointercancel', onPointerUp);
      canvas.addEventListener('contextmenu', onContextMenu);
      canvas.addEventListener('wheel', onWheel, { passive: false });

      const markerEls = Array.from(markersRef.current?.children ?? []) as HTMLElement[];
      const markerPoints = scene.keys.map(
        (key) => [key.anchor[0], key.anchor[2], -key.anchor[1]] as [number, number, number],
      );
      const scratch = new Vec3();

      const resize = () => {
        const rect = wrap.getBoundingClientRect();
        const width = Math.max(1, Math.round(rect.width));
        const height = Math.max(1, Math.round(rect.height));
        renderer.setSize(width, height);
        camera.perspective({ aspect: width / height });
      };
      resize();

      let raf = 0;
      let visible = true;
      const observer = new IntersectionObserver((entries) => {
        visible = entries.some((entry) => entry.isIntersecting);
      });
      observer.observe(wrap);

      const frame = () => {
        raf = requestAnimationFrame(frame);
        if (!visible || contextLost) return;
        if (autoRotate === true && !still && !dragging) {
          theta += 0.0025;
          applyCamera();
        }
        camera.updateMatrixWorld();
        renderer.render({ scene: sceneRoot, camera });
        const rect = canvas.getBoundingClientRect();
        for (let i = 0; i < markerEls.length; i++) {
          const marker = markerEls[i];
          const point = markerPoints[i];
          if (!marker || !point) continue;
          scratch.set(point[0], point[1], point[2]);
          camera.project(scratch);
          const x = (scratch.x * 0.5 + 0.5) * rect.width;
          const y = (1 - (scratch.y * 0.5 + 0.5)) * rect.height;
          const inside = scratch.z > -1 && scratch.z < 1;
          marker.style.transform = `translate(-50%,-50%) translate(${x}px, ${y}px)`;
          marker.style.opacity = inside ? '1' : '0';
        }
      };
      raf = requestAnimationFrame(frame);

      api = {
        resize,
        teardown: () => {
          cancelAnimationFrame(raf);
          observer.disconnect();
          canvas.removeEventListener('webglcontextlost', onLost as EventListener);
          canvas.removeEventListener('pointerdown', onPointerDown);
          canvas.removeEventListener('pointermove', onPointerMove);
          canvas.removeEventListener('pointerup', onPointerUp);
          canvas.removeEventListener('pointercancel', onPointerUp);
          canvas.removeEventListener('contextmenu', onContextMenu);
          canvas.removeEventListener('wheel', onWheel);
          apiRef.current = null;
          // Drop the canvas entirely; never call WEBGL_lose_context.
          canvas.remove();
        },
      };
    };

    const resizeObserver = new ResizeObserver(() => {
      if (api) api.resize();
      else if (wrap.clientWidth > 0 && wrap.clientHeight > 0) start();
    });
    resizeObserver.observe(wrap);

    if (wrap.clientWidth > 0 && wrap.clientHeight > 0) start();

    return () => {
      resizeObserver.disconnect();
      api?.teardown();
      api = null;
    };
  }, [scene, still, autoRotate]);

  return (
    <div ref={wrapRef} className="relative h-full w-full">
      <div ref={markersRef} className="pointer-events-none absolute inset-0">
        {scene.keys.map((key, i) => (
          <div
            key={key.id}
            className="absolute left-0 top-0 flex h-5 w-5 items-center justify-center rounded-full border border-white/35 bg-black/70 font-mono text-[10px] font-semibold text-white/90"
            style={{ transition: 'opacity 120ms linear' }}
          >
            {i + 1}
          </div>
        ))}
      </div>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-end p-2">
        <div className="pointer-events-auto flex flex-col gap-1">
          <ControlButton label="Orbit (drag to rotate)" active={mode === 'orbit'} onClick={() => setMode('orbit')}>↻</ControlButton>
          <ControlButton label="Drag (drag to pan)" active={mode === 'drag'} onClick={() => setMode('drag')}>✥</ControlButton>
          <ControlButton label="Zoom in" onClick={() => apiRef.current?.zoom(1)}>+</ControlButton>
          <ControlButton label="Zoom out" onClick={() => apiRef.current?.zoom(-1)}>−</ControlButton>
          <ControlButton label="Reset view" onClick={() => apiRef.current?.reset()}>⟲</ControlButton>
        </div>
      </div>
    </div>
  );
}

export default Model3dCanvas;
