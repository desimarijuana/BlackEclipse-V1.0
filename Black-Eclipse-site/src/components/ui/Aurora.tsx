import { Renderer, Program, Mesh, Color, Triangle } from 'ogl';
import { useEffect, useRef } from 'react';
import { resolveAuroraVisuals, stepSentiment } from '@/lib/aurora-sentiment';
import './Aurora.css';

const VERT = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const FRAG = `#version 300 es
precision highp float;

uniform float uTime;
uniform float uAmplitude;
uniform vec3 uColorStops[3];
uniform vec2 uResolution;
uniform float uBlend;

out vec4 fragColor;

vec3 permute(vec3 x) {
  return mod(((x * 34.0) + 1.0) * x, 289.0);
}

float snoise(vec2 v){
  const vec4 C = vec4(
      0.211324865405187, 0.366025403784439,
      -0.577350269189626, 0.024390243902439
  );
  vec2 i  = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);

  vec3 p = permute(
      permute(i.y + vec3(0.0, i1.y, 1.0))
    + i.x + vec3(0.0, i1.x, 1.0)
  );

  vec3 m = max(
      0.5 - vec3(
          dot(x0, x0),
          dot(x12.xy, x12.xy),
          dot(x12.zw, x12.zw)
      ), 
      0.0
  );
  m = m * m;
  m = m * m;

  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0*a0 + h*h);

  vec3 g;
  g.x  = a0.x  * x0.x  + h.x  * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

struct ColorStop {
  vec3 color;
  float position;
};

#define COLOR_RAMP(colors, factor, finalColor) {              \
  int index = 0;                                            \
  for (int i = 0; i < 2; i++) {                               \
     ColorStop currentColor = colors[i];                    \
     bool isInBetween = currentColor.position <= factor;    \
     index = int(mix(float(index), float(i), float(isInBetween))); \
  }                                                         \
  ColorStop currentColor = colors[index];                   \
  ColorStop nextColor = colors[index + 1];                  \
  float range = nextColor.position - currentColor.position; \
  float lerpFactor = (factor - currentColor.position) / range; \
  finalColor = mix(currentColor.color, nextColor.color, lerpFactor); \
}

void main() {
  vec2 uv = gl_FragCoord.xy / uResolution;
  
  ColorStop colors[3];
  colors[0] = ColorStop(uColorStops[0], 0.0);
  colors[1] = ColorStop(uColorStops[1], 0.5);
  colors[2] = ColorStop(uColorStops[2], 1.0);
  
  vec3 rampColor;
  COLOR_RAMP(colors, uv.x, rampColor);
  
  float height = snoise(vec2(uv.x * 2.0 + uTime * 0.1, uTime * 0.25)) * 0.5 * uAmplitude;
  height = exp(height);
  height = (uv.y * 2.0 - height + 0.2);
  float intensity = 0.6 * height;
  
  float midPoint = 0.20;
  float auroraAlpha = smoothstep(midPoint - uBlend * 0.5, midPoint + uBlend * 0.5, intensity);
  
  vec3 auroraColor = intensity * rampColor;
  
  fragColor = vec4(auroraColor * auroraAlpha, auroraAlpha);
}
`;

export interface AuroraProps {
  /** Legacy static palette. Ignored when `sentiment` is provided. */
  colorStops?: [string, string, string];
  amplitude?: number;
  blend?: number;
  speed?: number;
  time?: number;
  /**
   * Combined market + news sentiment in [-1, +1] (-1 extreme bearish, 0 neutral,
   * +1 extreme bullish). When set, it drives color + motion continuously and
   * overrides `colorStops`/`amplitude`/`speed`. The WebGL context is created
   * once and only uniforms are updated, so changing this never re-initializes GL.
   */
  sentiment?: number;
  /** Per-frame easing factor toward `sentiment` (0..1). Higher = snappier. */
  smoothing?: number;
}

export default function Aurora(props: AuroraProps) {
  const { colorStops = ['#02170f', '#3d9e63', '#02170f'], amplitude = 1.0, blend = 0.5 } = props;
  // Keep the latest props in a ref so the rAF loop can read them without the
  // effect (and therefore the WebGL context) ever being torn down / rebuilt.
  const propsRef = useRef<AuroraProps>(props);
  propsRef.current = props;
  // Smoothed sentiment lives entirely inside the animation loop.
  const sentimentRef = useRef<number>(props.sentiment ?? 0);

  const ctnDom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctn = ctnDom.current;
    if (!ctn) return;

    const renderer = new Renderer({
      alpha: true,
      premultipliedAlpha: true,
      antialias: true
    });
    const gl = renderer.gl;
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.canvas.style.backgroundColor = 'transparent';

    let program: Program | null = null;

    function resize() {
      if (!ctn) return;
      const width = ctn.offsetWidth;
      const height = ctn.offsetHeight;
      renderer.setSize(width, height);
      if (program) {
        program.uniforms.uResolution.value = [width, height];
      }
    }
    window.addEventListener('resize', resize);

    const geometry = new Triangle(gl);
    if (geometry.attributes.uv) {
      delete geometry.attributes.uv;
    }

    const colorStopsArray = colorStops.map(hex => {
      const c = new Color(hex);
      return [c.r, c.g, c.b];
    });

    program = new Program(gl, {
      vertex: VERT,
      fragment: FRAG,
      uniforms: {
        uTime: { value: 0 },
        uAmplitude: { value: amplitude },
        uColorStops: { value: colorStopsArray },
        uResolution: { value: [ctn.offsetWidth, ctn.offsetHeight] },
        uBlend: { value: blend }
      }
    });

    const mesh = new Mesh(gl, { geometry, program });
    ctn.appendChild(gl.canvas);

    let animateId = 0;
    let lastT = 0;
    const update = (t: number) => {
      animateId = requestAnimationFrame(update);
      const current = propsRef.current;
      const useSentiment = typeof current.sentiment === 'number' && Number.isFinite(current.sentiment);

      // Ease the displayed score toward the incoming one so sentiment ticks
      // (e.g. +0.03 → -0.02) never flash the aurora green/red. Converted to a
      // frame-rate-independent step from a 60fps reference so slow devices ease
      // at the same wall-clock rate instead of lagging behind.
      if (useSentiment) {
        const target = Math.max(-1, Math.min(1, current.sentiment as number));
        const base = current.smoothing ?? 0.04;
        const dt = lastT ? Math.min(0.25, (t - lastT) / 1000) : 1 / 60;
        const alpha = 1 - Math.pow(1 - base, dt * 60);
        sentimentRef.current = stepSentiment(sentimentRef.current, target, alpha);
      }
      lastT = t;

      // Resolve the effective palette + motion. Sentiment drives continuous
      // interpolation; without it the legacy static props are used verbatim.
      const vis = useSentiment ? resolveAuroraVisuals(sentimentRef.current) : null;
      const effectiveAmplitude = vis ? vis.amplitude : (current.amplitude ?? amplitude);
      const effectiveSpeed = vis ? vis.speed : (current.speed ?? 1.0);
      const effectiveBlend = vis ? vis.blend : (current.blend ?? blend);
      const stops = vis ? vis.colorStops : (current.colorStops ?? colorStops);

      // `time` / `speed` remain a valid manual override for external clocks.
      const { time = t * 0.01 } = current;
      program.uniforms.uTime.value = time * effectiveSpeed * 0.1;
      program.uniforms.uAmplitude.value = effectiveAmplitude;
      program.uniforms.uBlend.value = effectiveBlend;
      program.uniforms.uColorStops.value = stops.map(hex => {
        const c = new Color(hex);
        return [c.r, c.g, c.b];
      });
      renderer.render({ scene: mesh });
    };
    animateId = requestAnimationFrame(update);

    resize();

    return () => {
      cancelAnimationFrame(animateId);
      window.removeEventListener('resize', resize);
      if (ctn && gl.canvas.parentNode === ctn) {
        ctn.removeChild(gl.canvas);
      }
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [amplitude]);

  return <div ref={ctnDom} className="aurora-container" />;
}
