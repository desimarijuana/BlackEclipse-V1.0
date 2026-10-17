'use client';

// ── Model3dCanvas — the WebGL viewport (charcoal paper + graphite outline) ────
//
// Client-only (next/dynamic ssr:false). Receives an ALREADY COMPILED scene —
// world-space meshes + feature edges — and does one job: draw it, with explicit,
// scoped camera controls, selection, exploded/section views and numbered
// hotspots.
//
// Controls (all scoped to THIS canvas, never the page):
//  * drag                → orbit
//  * ctrl/cmd/right-drag → pan   ·  "Drag" mode button = drag pans
//  * wheel               → zoom (cursor over the model)  ·  pinch to zoom
//  * arrows / +− / 0     → orbit / zoom / reset (keyboard, when focused)
//  * buttons + sliders   → camera, exploded view, section, PNG snapshot
//
// Robustness: the <canvas> is created INSIDE the effect and removed on teardown
// (a fresh context every mount, never reusing a lost one, no `lose_context`),
// waits for a non-zero wrapper size, and handles `webglcontextlost`.

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Camera, Geometry, Mesh, Program, Raycast, Renderer, Transform, Vec3 } from 'ogl';
import type { CompiledModel3d } from '@/lib/model3d/compile';
import type { Model3dTone } from '@/lib/model3d/names';

const DEG = Math.PI / 180;
const FOV = 35;

// Flat sketch look: solids fill with the paper colour; `tone` only colours wires.
const PAPER: [number, number, number] = [0.086, 0.086, 0.094]; // #161618
const OUTLINE: [number, number, number] = [0.227, 0.243, 0.267]; // #3A3E44
const LIT_OUTLINE: [number, number, number] = [0.55, 0.60, 0.66];
const SELECTED_OUTLINE: [number, number, number] = [0.82, 0.87, 0.94];

const TONES: Record<Model3dTone, [number, number, number]> = {
  neutral: [0.74, 0.77, 0.80],
  info: [0.55, 0.68, 0.88],
  success: [0.52, 0.79, 0.62],
  warning: [0.86, 0.73, 0.44],
  danger: [0.87, 0.55, 0.55],
};

const CUT_OFF = 1e9;

const VERTEX = `
attribute vec3 position;
attribute vec3 normal;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
uniform mat3 normalMatrix;
varying vec3 vNormal;
varying vec3 vView;
varying vec3 vWorld;
void main() {
  vNormal = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vView = -mv.xyz;
  vWorld = position;
  gl_Position = projectionMatrix * mv;
}`;

const FRAGMENT = `
precision highp float;
uniform vec3 uFill;
uniform vec3 uLine;
uniform float uLit;
uniform float uSelected;
uniform float uOpacity;
uniform float uCut;
varying vec3 vNormal;
varying vec3 vView;
varying vec3 vWorld;

void main() {
  if (vWorld.x > uCut) discard;
  vec3 n = normalize(vNormal);
  vec3 v = normalize(vView);
  vec3 fill = mix(uFill, uFill * 1.5, max(uLit, uSelected * 0.5));
  vec3 line = mix(uLine, vec3(0.55, 0.60, 0.66), uLit);
  line = mix(line, vec3(0.82, 0.87, 0.94), uSelected);
  // Silhouette band: outline only where the surface turns edge-on.
  float f = 1.0 - max(dot(n, v), 0.0);
  float edge = smoothstep(0.55, 0.82, f);
  gl_FragColor = vec4(mix(fill, line, edge), uOpacity);
}`;

const EDGE_VERTEX = `
attribute vec3 position;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
varying vec3 vWorld;
void main() {
  vWorld = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const EDGE_FRAGMENT = `
precision highp float;
uniform vec3 uColor;
uniform float uOpacity;
uniform float uCut;
varying vec3 vWorld;
void main() {
  if (vWorld.x > uCut) discard;
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

const SHADOW_VERTEX = `
attribute vec3 position;
attribute vec2 uv;
uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const SHADOW_FRAGMENT = `
precision highp float;
uniform float uOpacity;
varying vec2 vUv;
void main() {
  float d = length(vUv);
  if (d > 1.0) discard;
  gl_FragColor = vec4(0.0, 0.0, 0.0, pow(1.0 - d, 2.0) * uOpacity);
}`;

const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v));

function vec3Of(t: [number, number, number]): Vec3 {
  return new Vec3(t[0], t[1], t[2]);
}

interface CanvasApi {
  zoom: (dir: number) => void;
  reset: () => void;
  rotate: (dTheta: number, dPhi: number) => void;
  setExplode: (t: number) => void;
  setSection: (t: number) => void;
  setContrast: (on: boolean) => void;
  setMeasure: (on: boolean) => void;
  snapshot: () => void;
}

export type Model3dMode = 'orbit' | 'drag';

export interface Model3dCanvasProps {
  scene: CompiledModel3d;
  litGroups: Set<string>;
  still: boolean;
  autoRotate?: boolean;
  selected?: string | null;
  onSelect?: (group: string | null) => void;
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

function downloadPng(dataUrl: string): void {
  const anchor = document.createElement('a');
  anchor.href = dataUrl;
  anchor.download = 'eclipse-model.png';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function Model3dCanvas({ scene, litGroups, still, autoRotate, selected, onSelect, onError }: Model3dCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<HTMLDivElement>(null);
  const litRef = useRef(litGroups);
  litRef.current = litGroups;
  const selectedRef = useRef<string | null>(selected ?? null);
  selectedRef.current = selected ?? null;
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const errorRef = useRef(onError);
  errorRef.current = onError;

  const [mode, setMode] = useState<Model3dMode>('orbit');
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const [explode, setExplode] = useState(0);
  const [section, setSection] = useState(1);
  const [contrast, setContrast] = useState(false);
  const [measure, setMeasure] = useState(false);
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const measureLabelRef = useRef<HTMLSpanElement>(null);
  const apiRef = useRef<CanvasApi | null>(null);

  // Authored-lit parts plus the active stage's lit set — drives the hotspot
  // highlight so the numbered markers light up with the stage / selection.
  const highlightedGroups = new Set<string>(litGroups);
  for (const part of scene.parts) if (part.lit) highlightedGroups.add(part.group);

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
          preserveDrawingBuffer: true,
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
          uSelected: { value: 0 },
          uOpacity: { value: 1 },
          uCut: { value: CUT_OFF },
        },
      });
      const edgeProgram = new Program(gl, {
        vertex: EDGE_VERTEX,
        fragment: EDGE_FRAGMENT,
        uniforms: { uColor: { value: OUTLINE }, uOpacity: { value: 1 }, uCut: { value: CUT_OFF } },
      });
      const lineProgram = new Program(gl, {
        vertex: LINE_VERTEX,
        fragment: LINE_FRAGMENT,
        transparent: true,
        depthWrite: false,
        uniforms: { uColor: { value: [0.6, 0.64, 0.68] }, uOpacity: { value: 0.5 }, uRange: { value: 1 } },
      });
      const shadowProgram = new Program(gl, {
        vertex: SHADOW_VERTEX,
        fragment: SHADOW_FRAGMENT,
        transparent: true,
        depthWrite: false,
        uniforms: { uOpacity: { value: 0.5 } },
      });

      const sceneRoot = new Transform();
      sceneRoot.rotation.x = -Math.PI / 2;
      let baseOutline: [number, number, number] = OUTLINE;

      const pickMeshes: Mesh[] = [];
      const meshGroup = new Map<Mesh, string>();
      // Explode: every solid+edge mesh of a group, with its outward direction.
      const explodeSets: Array<{ meshes: Mesh[]; dir: Vec3 }> = [];
      const sceneCenter: [number, number, number] = [
        (scene.bounds.min[0] + scene.bounds.max[0]) / 2,
        (scene.bounds.min[1] + scene.bounds.max[1]) / 2,
        (scene.bounds.min[2] + scene.bounds.max[2]) / 2,
      ];

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
          const selected = selectedRef.current === part.group;
          program.uniforms.uLit.value = lit ? 1 : 0;
          program.uniforms.uSelected.value = selected ? 1 : 0;
          program.uniforms.uOpacity.value = alpha;
        });
        mesh.setParent(sceneRoot);
        pickMeshes.push(mesh);
        meshGroup.set(mesh, part.group);

        const groupMeshes: Mesh[] = [mesh];
        if (part.edges.length >= 6) {
          const edgeMesh = new Mesh(gl, {
            geometry: new Geometry(gl, { position: { size: 3, data: part.edges } }),
            program: edgeProgram,
            mode: gl.LINES,
          });
          edgeMesh.onBeforeRender(() => {
            const selected = selectedRef.current === part.group;
            const lit = part.lit || litRef.current.has(part.group);
            edgeProgram.uniforms.uColor.value = selected
              ? SELECTED_OUTLINE
              : lit
                ? LIT_OUTLINE
                : baseOutline;
          });
          edgeMesh.setParent(sceneRoot);
          groupMeshes.push(edgeMesh);
        }
        const cx = (part.bounds.min[0] + part.bounds.max[0]) / 2;
        const cy = (part.bounds.min[1] + part.bounds.max[1]) / 2;
        const cz = (part.bounds.min[2] + part.bounds.max[2]) / 2;
        let dx = cx - sceneCenter[0], dy = cy - sceneCenter[1], dz = cz - sceneCenter[2];
        const len = Math.hypot(dx, dy, dz) || 1;
        dx /= len; dy /= len; dz /= len;
        explodeSets.push({ meshes: groupMeshes, dir: new Vec3(dx, dy, dz) });
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

      // Soft contact shadow on the ground (z = 0) so the machine sits on it.
      const shadowRadius = Math.max(span * 1.15, 20);
      const shadowGeom = new Geometry(gl, {
        position: { size: 3, data: new Float32Array([-shadowRadius, -shadowRadius, 0, shadowRadius, -shadowRadius, 0, shadowRadius, shadowRadius, 0, -shadowRadius, shadowRadius, 0]) },
        uv: { size: 2, data: new Float32Array([-1, -1, 1, -1, 1, 1, -1, 1]) },
        index: { data: new Uint16Array([0, 1, 2, 0, 2, 3]) },
      });
      const shadow = new Mesh(gl, { geometry: shadowGeom, program: shadowProgram });
      shadow.position.set(gcx, gcy, 0);
      shadow.setParent(sceneRoot);

      // Measurement: two picked points become one line + a distance readout.
      const measurePts: number[][] = [];
      const measureGeom = new Geometry(gl, { position: { size: 3, data: new Float32Array(0) } });
      const measureLine = new Mesh(gl, { geometry: measureGeom, program: lineProgram, mode: gl.LINES });
      measureLine.frustumCulled = false;
      measureLine.onBeforeRender(() => {
        lineProgram.uniforms.uColor.value = [0.96, 0.98, 1.0];
        lineProgram.uniforms.uOpacity.value = 0.95;
        lineProgram.uniforms.uRange.value = 1e9;
      });
      measureLine.setParent(sceneRoot);
      const clearMeasure = () => {
        measurePts.length = 0;
        measureGeom.attributes.position.data = new Float32Array(0);
        measureGeom.attributes.position.needsUpdate = true;
        if (measureLabelRef.current) measureLabelRef.current.textContent = '';
      };
      let measureOn = false;

      scene.wires.forEach((wire) => {
        const mesh = new Mesh(gl, {
          geometry: new Geometry(gl, { position: { size: 3, data: new Float32Array([...wire.from, ...wire.to]) } }),
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

      // Leader lines: a short stroke from each hotspot's anchor outward, so the
      // numbered marker sits just off the part and visibly points at it.
      const leaderLen = Math.max(span * 0.09, 3);
      const leaderPoints = scene.keys.flatMap((key) => {
        const dx = key.anchor[0] - sceneCenter[0];
        const dy = key.anchor[1] - sceneCenter[1];
        const dz = key.anchor[2] - sceneCenter[2];
        const len = Math.hypot(dx, dy, dz) || 1;
        return [
          key.anchor[0], key.anchor[1], key.anchor[2],
          key.anchor[0] + (dx / len) * leaderLen,
          key.anchor[1] + (dy / len) * leaderLen,
          key.anchor[2] + (dz / len) * leaderLen,
        ];
      });
      if (leaderPoints.length) {
        const leaderMesh = new Mesh(gl, {
          geometry: new Geometry(gl, { position: { size: 3, data: new Float32Array(leaderPoints) } }),
          program: edgeProgram,
          mode: gl.LINES,
        });
        leaderMesh.frustumCulled = false;
        leaderMesh.onBeforeRender(() => {
          edgeProgram.uniforms.uColor.value = [0.7, 0.76, 0.84];
          edgeProgram.uniforms.uCut.value = CUT_OFF;
        });
        leaderMesh.setParent(sceneRoot);
      }

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

      const extent = Math.max(scene.bounds.max[0] - scene.bounds.min[0], scene.bounds.max[1] - scene.bounds.min[1], scene.bounds.max[2] - scene.bounds.min[2]);
      const zoom = (dir: number) => {
        radius = clamp(radius * (dir > 0 ? 0.85 : 1.18), minRadius, maxRadius);
        applyCamera();
      };
      const rotate = (dTheta: number, dPhi: number) => {
        theta += dTheta;
        phi = clamp(phi + dPhi, -1.45, 1.45);
        applyCamera();
      };
      const reset = () => {
        target = new Vec3(base.x, base.y, base.z);
        radius = scene.distance;
        theta = scene.azimuth * DEG;
        phi = scene.elevation * DEG;
        applyCamera();
      };
      let explodeT = 0;
      const setExploded = (t: number) => {
        explodeT = t;
        const amount = t * 0.6 * Math.max(extent, 40);
        for (const set of explodeSets) {
          set.meshes.forEach((m) => m.position.set(set.dir.x * amount, set.dir.y * amount, set.dir.z * amount));
        }
      };
      const modelSpanX = Math.max(scene.bounds.max[0] - scene.bounds.min[0], 1);
      const setSectioned = (t: number) => {
        // 1 = no cut; below that, cut the model along its X axis.
        const cut = t >= 0.999 ? CUT_OFF : scene.bounds.min[0] - modelSpanX * 0.05 + t * modelSpanX * 1.1;
        program.uniforms.uCut.value = cut;
        edgeProgram.uniforms.uCut.value = cut;
        grid.visible = t >= 0.999;
      };

      const snapshot = () => {
        camera.updateMatrixWorld();
        renderer.render({ scene: sceneRoot, camera });
        downloadPng(canvas.toDataURL('image/png'));
      };

      const setContrast = (on: boolean) => {
        baseOutline = on ? [0.5, 0.55, 0.6] : OUTLINE;
        program.uniforms.uLine.value = on ? [0.5, 0.55, 0.6] : OUTLINE;
        program.uniforms.uFill.value = on ? [0.16, 0.17, 0.18] : PAPER;
      };

      apiRef.current = { zoom, reset, rotate, setExplode: setExploded, setSection: setSectioned, setContrast, setMeasure: (on) => { measureOn = on; if (!on) clearMeasure(); if (!on && measureLabelRef.current) measureLabelRef.current.textContent = ''; }, snapshot };

      // ── Pointer: orbit / pan / pinch / click-select ──────────────────────
      const raycaster = new Raycast();
      const pointers = new Map<number, { x: number; y: number }>();
      let dragging: 'rotate' | 'pan' | null = null;
      let lastX = 0;
      let lastY = 0;
      let downX = 0;
      let downY = 0;
      let moved = false;
      let pinchStart = 0;

      const onPointerDown = (event: PointerEvent) => {
        if (event.button !== 0 && event.button !== 2) return;
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        if (pointers.size === 2) {
          const [a, b] = [...pointers.values()];
          pinchStart = Math.hypot(a!.x - b!.x, a!.y - b!.y) || 1;
          dragging = null;
          return;
        }
        const pan = event.button === 2 || modeRef.current === 'drag' || event.ctrlKey || event.metaKey;
        dragging = pan ? 'pan' : 'rotate';
        lastX = downX = event.clientX;
        lastY = downY = event.clientY;
        moved = false;
        canvas.style.cursor = 'grabbing';
        try { canvas.setPointerCapture(event.pointerId); } catch { /* ignore */ }
        event.preventDefault();
      };
      const onPointerMove = (event: PointerEvent) => {
        if (pointers.has(event.pointerId)) pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        if (pointers.size >= 2) {
          const [a, b] = [...pointers.values()];
          const dist = Math.hypot(a!.x - b!.x, a!.y - b!.y) || 1;
          radius = clamp(radius * (pinchStart / dist), minRadius, maxRadius);
          pinchStart = dist;
          applyCamera();
          return;
        }
        if (!dragging) return;
        const dx = event.clientX - lastX;
        const dy = event.clientY - lastY;
        if (Math.abs(event.clientX - downX) + Math.abs(event.clientY - downY) > 4) moved = true;
        lastX = event.clientX;
        lastY = event.clientY;
        if (dragging === 'rotate') {
          rotate(-dx * 0.006, dy * 0.006);
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
          applyCamera();
        }
      };
      const pickAt = (clientX: number, clientY: number) => {
        const rect = canvas.getBoundingClientRect();
        const nx = ((clientX - rect.left) / rect.width) * 2 - 1;
        const ny = -(((clientY - rect.top) / rect.height) * 2 - 1);
        raycaster.castMouse(camera, [nx, ny]);
        const hits = raycaster.intersectMeshes(pickMeshes, { cullFace: false, maxDistance: scene.distance * 8 });
        onSelectRef.current?.(hits[0] ? meshGroup.get(hits[0]) ?? null : null);
      };
      const pickPoint = (clientX: number, clientY: number) => {
        const rect = canvas.getBoundingClientRect();
        const nx = ((clientX - rect.left) / rect.width) * 2 - 1;
        const ny = -(((clientY - rect.top) / rect.height) * 2 - 1);
        raycaster.castMouse(camera, [nx, ny]);
        const hits = raycaster.intersectMeshes(pickMeshes, { cullFace: false, maxDistance: scene.distance * 8 });
        const point = hits[0]?.hit?.point;
        if (!point) return;
        // World is Y-up; the model is Z-up — convert back through the root rotation.
        measurePts.push([point.x, -point.z, point.y]);
        if (measurePts.length === 2) {
          const a = measurePts[0]!, b = measurePts[1]!;
          measureGeom.attributes.position.data = new Float32Array([a[0], a[1], a[2], b[0], b[1], b[2]]);
          measureGeom.attributes.position.needsUpdate = true;
          const dist = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
          if (measureLabelRef.current) measureLabelRef.current.textContent = `${dist.toFixed(1)} units`;
          measurePts.length = 0;
        }
      };
      const onPointerUp = (event: PointerEvent) => {
        pointers.delete(event.pointerId);
        if (pointers.size < 2) pinchStart = 0;
        if (!dragging) return;
        const wasDrag = moved;
        dragging = null;
        canvas.style.cursor = 'grab';
        try { canvas.releasePointerCapture(event.pointerId); } catch { /* ignore */ }
        if (!wasDrag && event.button === 0) {
          if (measureOn) pickPoint(event.clientX, event.clientY);
          else pickAt(event.clientX, event.clientY);
        }
      };
      const onContextMenu = (event: Event) => event.preventDefault();
      const onWheel = (event: WheelEvent) => {
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
      const markerDirs = scene.keys.map((key) => {
        const dx = key.anchor[0] - sceneCenter[0];
        const dy = key.anchor[1] - sceneCenter[1];
        const dz = key.anchor[2] - sceneCenter[2];
        const len = Math.hypot(dx, dy, dz) || 1;
        return [dx / len, dz / len, -dy / len] as [number, number, number];
      });
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
          rotate(0.0025, 0);
        }
        camera.updateMatrixWorld();
        renderer.render({ scene: sceneRoot, camera });
        const rect = canvas.getBoundingClientRect();
        const explodeAmount = explodeT * 0.6 * Math.max(extent, 40);
        for (let i = 0; i < markerEls.length; i++) {
          const marker = markerEls[i];
          const point = markerPoints[i];
          if (!marker || !point) continue;
          const dir = markerDirs[i]!;
          scratch.set(
            point[0] + dir[0] * (leaderLen + explodeAmount),
            point[1] + dir[1] * (leaderLen + explodeAmount),
            point[2] + dir[2] * (leaderLen + explodeAmount),
          );
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

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const api = apiRef.current;
    if (!api) return;
    const key = event.key;
    if (key === 'ArrowLeft') { api.rotate(-0.08, 0); event.preventDefault(); }
    else if (key === 'ArrowRight') { api.rotate(0.08, 0); event.preventDefault(); }
    else if (key === 'ArrowUp') { api.rotate(0, -0.06); event.preventDefault(); }
    else if (key === 'ArrowDown') { api.rotate(0, 0.06); event.preventDefault(); }
    else if (key === '+' || key === '=') { api.zoom(1); event.preventDefault(); }
    else if (key === '-' || key === '_') { api.zoom(-1); event.preventDefault(); }
    else if (key === '0') { api.reset(); event.preventDefault(); }
  };

  return (
    <div ref={wrapRef} className="relative h-full w-full" tabIndex={0} onKeyDown={onKeyDown}>
      <div ref={markersRef} className="pointer-events-none absolute inset-0">
        {scene.keys.map((key, i) => {
          const active = selected === key.id;
          const lit = !active && highlightedGroups.has(key.id);
          return (
            <div
              key={key.id}
              data-number={i + 1}
              className={
                'absolute left-0 top-0 flex h-5 w-5 items-center justify-center rounded-full border font-mono text-[10px] font-semibold transition-colors ' +
                (active
                  ? 'border-white bg-white text-black'
                  : lit
                    ? 'border-white/85 bg-white/25 text-white'
                    : 'border-white/35 bg-black/70 text-white/90')
              }
              style={{ transition: 'opacity 120ms linear' }}
            >
              {i + 1}
            </div>
          );
        })}
      </div>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-2">
        <div className="pointer-events-auto flex flex-col gap-1 rounded-md border border-white/10 bg-black/45 px-2 py-1.5 backdrop-blur-sm">
          <label className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wide text-white/55">
            Explode
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={explode}
              onChange={(e) => { const v = Number(e.target.value); setExplode(v); apiRef.current?.setExplode(v); }}
              className="h-1 w-20 accent-white/70"
            />
          </label>
          <label className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wide text-white/55">
            Section
            <input
              type="range"
              min={0}
              max={1}
              step={0.02}
              value={section}
              onChange={(e) => { const v = Number(e.target.value); setSection(v); apiRef.current?.setSection(v); }}
              className="h-1 w-20 accent-white/70"
            />
          </label>
          <span ref={measureLabelRef} className="font-mono text-[10px] text-white/80" />
        </div>
        <div className="pointer-events-auto flex flex-col gap-1">
          <ControlButton label="Orbit (drag to rotate)" active={mode === 'orbit'} onClick={() => setMode('orbit')}>↻</ControlButton>
          <ControlButton label="Drag (drag to pan)" active={mode === 'drag'} onClick={() => setMode('drag')}>✥</ControlButton>
          <ControlButton label="Zoom in" onClick={() => apiRef.current?.zoom(1)}>+</ControlButton>
          <ControlButton label="Zoom out" onClick={() => apiRef.current?.zoom(-1)}>−</ControlButton>
          <ControlButton label="Reset view" onClick={() => apiRef.current?.reset()}>⟲</ControlButton>
          <ControlButton
            label="Measure (click two points)"
            active={measure}
            onClick={() => { const v = !measure; setMeasure(v); apiRef.current?.setMeasure(v); }}
          >↔</ControlButton>
          <ControlButton
            label="High contrast"
            active={contrast}
            onClick={() => { const v = !contrast; setContrast(v); apiRef.current?.setContrast(v); }}
          >◐</ControlButton>
          <ControlButton label="Save PNG snapshot" onClick={() => apiRef.current?.snapshot()}>⤓</ControlButton>
        </div>
      </div>
    </div>
  );
}

export default Model3dCanvas;
