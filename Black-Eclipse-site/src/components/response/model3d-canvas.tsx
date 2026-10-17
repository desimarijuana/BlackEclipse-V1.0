'use client';

// ── Model3dCanvas — the WebGL viewport ────────────────────────────────────────
//
// Client-only (loaded via next/dynamic ssr:false). Receives an ALREADY COMPILED
// scene — world-space meshes — and does one job: put triangles on screen with
// orbit/zoom/pan, real lighting and numbered hotspots. It computes no geometry
// and parses no model output.
//
// Uses `ogl` (already a dependency, ~15 KB) so there is no new bundle weight.
// The context is created once and torn down on unmount; rendering pauses while
// the figure is off-screen.

import { useEffect, useRef } from 'react';
import { Camera, Geometry, Mesh, Orbit, Program, Renderer, Transform, Vec3 } from 'ogl';
import type { CompiledModel3d } from '@/lib/model3d/compile';
import type { Model3dTone } from '@/lib/model3d/names';

const DEG = Math.PI / 180;

const TONES: Record<Model3dTone, [number, number, number]> = {
  neutral: [0.58, 0.61, 0.66],
  info: [0.36, 0.56, 0.95],
  success: [0.3, 0.75, 0.5],
  warning: [0.86, 0.67, 0.25],
  danger: [0.86, 0.42, 0.42],
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
uniform vec3 uColor;
uniform float uLit;
uniform float uOpacity;
uniform float uEmissive;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vec3 n = normalize(vNormal);
  vec3 v = normalize(vView);
  vec3 key = normalize(vec3(0.42, 0.68, 0.85));
  float diff = max(dot(n, key), 0.0);
  vec3 fillDir = normalize(vec3(-0.6, -0.35, 0.35));
  float fill = max(dot(n, fillDir), 0.0) * 0.32;
  float rim = pow(1.0 - max(dot(n, v), 0.0), 2.4) * 0.55;
  vec3 col = uColor * (0.30 + 0.80 * diff + fill) + vec3(rim) * 0.45;
  col = mix(col, uColor * 1.55 + vec3(0.22), uLit);
  col += uColor * uEmissive;
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), uOpacity);
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

function vec3Of(t: [number, number, number]): Vec3 {
  return new Vec3(t[0], t[1], t[2]);
}

export interface Model3dCanvasProps {
  scene: CompiledModel3d;
  litGroups: Set<string>;
  still: boolean;
  autoRotate?: boolean;
  onError?: (message: string) => void;
}

export function Model3dCanvas({ scene, litGroups, still, autoRotate, onError }: Model3dCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<HTMLDivElement>(null);
  const litRef = useRef(litGroups);
  litRef.current = litGroups;

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;

    let renderer: Renderer;
    try {
      renderer = new Renderer({ canvas, dpr: Math.min(2, window.devicePixelRatio || 1), alpha: false, antialias: true });
    } catch {
      onError?.('WebGL is unavailable in this browser.');
      return;
    }
    const gl = renderer.gl;
    gl.clearColor(0.045, 0.045, 0.05, 1);
    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const program = new Program(gl, {
      vertex: VERTEX,
      fragment: FRAGMENT,
      uniforms: {
        uColor: { value: [0.5, 0.5, 0.5] },
        uLit: { value: 0 },
        uOpacity: { value: 1 },
        uEmissive: { value: 0 },
      },
    });
    const lineProgram = new Program(gl, {
      vertex: LINE_VERTEX,
      fragment: LINE_FRAGMENT,
      transparent: true,
      depthWrite: false,
      uniforms: { uColor: { value: [0.4, 0.45, 0.5] }, uOpacity: { value: 0.5 }, uRange: { value: 1 } },
    });

    const sceneRoot = new Transform();
    // The compiler is Z-up (the finance/world convention); OGL's Orbit is Y-up.
    // Rotate the whole scene once so the turntable orbits the vertical axis.
    sceneRoot.rotation.x = -Math.PI / 2;
    const meshes: Array<{ mesh: Mesh; group: string; authored: boolean; color: [number, number, number]; emissive: number }> = [];

    for (const part of scene.parts) {
      const geometry = new Geometry(gl, {
        position: { size: 3, data: part.mesh.positions },
        normal: { size: 3, data: part.mesh.normals },
        index: { data: part.mesh.indices },
      });
      const color = TONES[part.tone] ?? TONES.neutral;
      const bright = part.tone !== 'neutral' ? 1.08 : part.material === 'metal' ? 1.0 : 0.92;
      const emissive = part.material === 'emissive' ? 0.85 : 0;
      const mesh = new Mesh(gl, { geometry, program });
      const alpha = Math.max(0.25, part.opacity);
      mesh.onBeforeRender(() => {
        const lit = part.lit || litRef.current.has(part.group);
        program.uniforms.uColor.value = [color[0] * bright, color[1] * bright, color[2] * bright];
        program.uniforms.uLit.value = lit ? 1 : 0;
        program.uniforms.uOpacity.value = alpha;
        program.uniforms.uEmissive.value = emissive;
      });
      mesh.setParent(sceneRoot);
      meshes.push({ mesh, group: part.group, authored: part.lit, color, emissive });
    }

    // Ground grid (z = 0), fading out at the scene edge.
    const span = Math.max(
      scene.bounds.max[0] - scene.bounds.min[0],
      scene.bounds.max[1] - scene.bounds.min[1],
      40,
    ) * 0.75;
    const cx = (scene.bounds.min[0] + scene.bounds.max[0]) / 2;
    const cy = (scene.bounds.min[1] + scene.bounds.max[1]) / 2;
    const gridLines: number[] = [];
    const step = span / 8;
    for (let i = -8; i <= 8; i++) {
      gridLines.push(cx + i * step, cy - span, 0, cx + i * step, cy + span, 0);
      gridLines.push(cx - span, cy + i * step, 0, cx + span, cy + i * step, 0);
    }
    const grid = new Mesh(gl, {
      geometry: new Geometry(gl, { position: { size: 3, data: new Float32Array(gridLines) } }),
      program: lineProgram,
      mode: gl.LINES,
    });
    lineProgram.uniforms.uRange.value = span * 1.45;
    grid.onBeforeRender(() => {
      lineProgram.uniforms.uColor.value = [0.42, 0.47, 0.53];
      lineProgram.uniforms.uOpacity.value = 0.34;
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
        lineProgram.uniforms.uOpacity.value = wire.dotted ? 0.55 : wire.dashed ? 0.7 : 0.95;
        lineProgram.uniforms.uRange.value = 1e9;
      });
      mesh.setParent(sceneRoot);
    });

    const camera = new Camera(gl, { fov: 35, near: 0.1, far: scene.distance * 12 });
    // Scene is rotated into Y-up below; express target/camera in that space.
    const target = vec3Of([scene.target[0], scene.target[2], -scene.target[1]]);
    const az = scene.azimuth * DEG;
    const el = scene.elevation * DEG;
    camera.position.set(
      target.x + scene.distance * Math.cos(el) * Math.sin(az),
      target.y + scene.distance * Math.sin(el),
      target.z + scene.distance * Math.cos(el) * Math.cos(az),
    );
    camera.lookAt(target);

    const orbit = new Orbit(camera, {
      target,
      enablePan: true,
      enableZoom: true,
      minDistance: scene.distance * 0.35,
      maxDistance: scene.distance * 4,
      autoRotate: autoRotate === true && !still,
      autoRotateSpeed: 0.6,
      ease: 0.12,
      inertia: 0.12,
    });
    orbit.forcePosition();

    const markers = Array.from(markersRef.current?.children ?? []) as HTMLElement[];
    const markerPoints = scene.keys.map((key) => vec3Of([key.anchor[0], key.anchor[2], -key.anchor[1]]));

    let raf = 0;
    let visible = true;
    const observer = new IntersectionObserver((entries) => {
      visible = entries.some((entry) => entry.isIntersecting);
    });
    observer.observe(wrap);

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width));
      const height = Math.max(1, Math.round(rect.height));
      renderer.setSize(width, height);
      camera.perspective({ aspect: width / height });
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(wrap);

    const frame = () => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      orbit.update();
      camera.updateMatrixWorld();
      renderer.render({ scene: sceneRoot, camera });
      for (let i = 0; i < markers.length; i++) {
        const marker = markers[i];
        const point = markerPoints[i];
        if (!marker || !point) continue;
        camera.project(point);
        const rect = canvas.getBoundingClientRect();
        const x = (point.x * 0.5 + 0.5) * rect.width;
        const y = (1 - (point.y * 0.5 + 0.5)) * rect.height;
        const inside = point.z > -1 && point.z < 1;
        marker.style.transform = `translate(-50%,-50%) translate(${x}px, ${y}px)`;
        marker.style.opacity = inside ? '1' : '0';
      }
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      resizeObserver.disconnect();
      orbit.remove();
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
    // The scene object is memoized by the caller; rebuild only when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene]);

  return (
    <div ref={wrapRef} className="relative h-full w-full">
      <canvas ref={canvasRef} className="block h-full w-full" aria-hidden="true" />
      <div ref={markersRef} className="pointer-events-none absolute inset-0">
        {scene.keys.map((key, i) => (
          <div
            key={key.id}
            className="absolute left-0 top-0 flex h-5 w-5 items-center justify-center rounded-full border border-white/40 bg-black/70 font-mono text-[10px] font-semibold text-white/90"
            style={{ transition: 'opacity 120ms linear' }}
          >
            {i + 1}
          </div>
        ))}
      </div>
    </div>
  );
}

export default Model3dCanvas;
