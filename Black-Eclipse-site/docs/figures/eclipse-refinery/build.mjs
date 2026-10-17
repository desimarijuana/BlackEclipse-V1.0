import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";
import * as G from "./kit/lathe.mjs";
import { tubePieces, tubeSvg } from "./kit/tube.mjs";
import { kitScript } from "./scripts/inline-kit.mjs";
import { MODEL, marketFill, regimeAt } from "./model.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--light") ? "light" : "dark";

const WIDTH = 940;
const HEIGHT = 600;

// ---------------------------------------------------------------------------
// Layout (world units: x, y on the floor, z up)
// ---------------------------------------------------------------------------
const PLATE = { x: -218, y: -74, w: 436, d: 156, r: 10 };
const PLATE_H = 12;
const FOOT_H = 6;

// Intake hopper (the scrapers)
const HX = -168;
const HY = -6;
const HOP_TOP = 54;
const HOP_BOT = 24;

// Vault (JDDS)
const VX = 0;
const VY = 0;
const V_R = 28;
const V_Z = 8;
const V_TOP = 90;

// Sight glass beside the vault (live level)
const SX = VX + 40;
const SY = VY - 22;
const S_Z0 = 14;
const S_Z1 = 74;

// Manifold header
const MX = 58;
const M_YS = [-42, -14, 14, 42];
const M_Z = 50;

// Instrument bench
const BENCH = { x: 88, y: -60, w: 66, d: 120, r: 6 };
const BENCH_TOP = 34;
const IX = 121;
const INDUST_ZS = 46;

// Gantry over the vault (the agent)
const G_L = -46;
const G_R = 50;
const G_TOP = 116;

// Aurora arc behind
const A_C = [0, -44, 34];
const A_R0 = 92;
const A_R1 = 108;

// ---------------------------------------------------------------------------
// Projection
// ---------------------------------------------------------------------------
const extremes = [
  ...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0),
  [HX, HY, HOP_TOP + 16],
  [VX, VY, V_TOP + 24],
  [G_L, 0, G_TOP + 4],
  [G_R, 0, G_TOP + 4],
  [A_C[0], A_C[1], A_C[2] + A_R1],
  [BENCH.x + BENCH.w, BENCH.y + BENCH.d, BENCH_TOP + 22],
];
if (theme) extremes.push([0, 0, 0]);
const P = k.fitProjection(extremes, WIDTH, HEIGHT, { pad: 30, azimuth: 40, elevation: 33 });

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const DD = (points, style) => k.dotsSvg(points, style);
const V = G.viewOf(P);

const items = [];
const add = (svg, where, bias = 0) =>
  items.push({ key: G.dot3(where, V) + bias, svg });

// A pipe route: fillets it, splits into depth-sorted chunks, returns a list of
// { key, svg } items. Also returns the filleted polyline for flanges/labels.
function pipe(points, radius, opts = {}) {
  const route = G.fillet(points, opts.bend ?? Math.max(4, radius * 2.6), 8, {
    P,
    tube: radius,
    margin: 1.3,
  });
  const pieces = tubePieces(route, radius, P, {
    maxLength: opts.maxLength ?? 16,
    gaps: opts.gaps ?? [],
    breaks: opts.breaks ?? [],
    rings: opts.rings,
    caps: opts.caps,
  });
  const out = [];
  for (const piece of pieces) {
    const svg = tubeSvg(piece, { tone: opts.tone ?? "hi" });
    out.push({ key: G.dot3(piece.mid, V) + (opts.bias ?? 0), svg, mid: piece.mid });
  }
  return { route, pieces: out, length: G.pathLength(route) };
}

const flange = (point, axis, r, t = 4, bias = 0.1) => {
  const u = G.unit3(axis);
  const c = G.sub3(point, G.mul3(u, t / 2));
  const F = G.frameAlong(c, u);
  add(S(G.disc(-t / 2, t / 2, r, F, P), { tone: "mid" }), point, bias);
  const dots = G.dotsOf(F, t / 2, r * 0.7, 8, P, { all: true });
  if (dots.length) add(DD(dots, { size: 0.42 }), point, bias + 0.01);
};

const byDepth = (pts) =>
  [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));

// ---------------------------------------------------------------------------
// Base plate (the app shell: one page, one plate)
// ---------------------------------------------------------------------------
function base() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 26))) {
    out.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "lo" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "lo" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "faint" }));
  const screws = k.corners(PLATE, 12);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.3, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(DD(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));

  // Datum ruler along the near edge
  const strip = { x: PLATE.x + 16, y: PLATE.y + PLATE.d - 15, w: PLATE.w - 120, d: 7, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 4, strip.x + strip.w - 4, 4, 5, strip.y + 0.8, 0.6, [2, 3.6], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(DD([at([strip.x + 2, strip.y + 3.5, 0.6]), at([strip.x + strip.w - 2, strip.y + 3.5, 0.6])], { size: 0.45 }));

  // Nameplate
  const plate = { x: PLATE.x + 16, y: PLATE.y + 10, w: 84, d: 22, r: 2 };
  out.push(S(k.slabOf(plate, 0, 1, P, 4), { tone: "lo", crease: "none" }));
  out.push(L(k.planOutline(k.insetPlan(plate, 1.6), 1, P), { tone: "faint" }));
  const rules = [0.82, 0.62, 0.4];
  rules.forEach((f, i) => {
    out.push(
      L(k.lineOnTop([plate.x + 4, plate.y + 5 + i * 5], [plate.x + 4 + (plate.w - 8) * f, plate.y + 5 + i * 5], 1, P), {
        tone: "lo",
        free: true,
      }),
    );
  });
  out.push(DD([at([plate.x + 2.4, plate.y + plate.d - 2.4, 1]), at([plate.x + plate.w - 2.4, plate.y + 2.4, 1])], { size: 0.45 }));
  return out.join("");
}

// ---------------------------------------------------------------------------
// Intake hopper + transfer line (the scrapers)
// ---------------------------------------------------------------------------
function intake() {
  const out = [];
  const coneF = G.frameAlong([HX, HY, 0], [0, 0, 1]);
  // Funnel: straight cone (no wobble), a rim collar and a throat.
  out.push(S(G.solidOf([[HOP_BOT, 9], [HOP_TOP, 30]], coneF, P, { smooth: false }), { tone: "mid" }));
  out.push(S(k.cylinder(HX, HY, 31, HOP_TOP, 3, P, 64, 0.6), { tone: "mid" }));
  out.push(L(G.arcOf(coneF, HOP_TOP, 30, P, { least: -1 }), { tone: "faint" }));
  out.push(S(k.cylinder(HX, HY, 10, HOP_BOT - 5, 5, P, 40), { tone: "mid" }));
  out.push(k.fadedSvg(G.ribsOf(coneF, HOP_BOT + 2, HOP_TOP - 2, 15, 20, P, { r1: 27, fade: [0.08, 0.5] }), { tone: "faint" }));

  // Three feed necks on the rim (TradingView · yfinance · RSS/crypto)
  for (const a of [Math.PI / 2, Math.PI * 0.83, Math.PI * 0.17]) {
    const nx = HX + Math.cos(a) * 22;
    const ny = HY + Math.sin(a) * 22;
    out.push(S(k.cylinder(nx, ny, 5, HOP_TOP + 3, 14, P, 28), { tone: "hi" }));
    out.push(L(k.knurl(nx, ny, 5, HOP_TOP + 4, HOP_TOP + 16, 24, P), { tone: "lo" }));
    out.push(S(k.cylinder(nx, ny, 6.5, HOP_TOP + 17, 3, P, 28, 0.5), { tone: "mid" }));
    out.push(L(k.sideArc(nx, ny, 6.5, HOP_TOP + 17, P, 24), { tone: "faint" }));
    out.push(DD([at([nx, ny, HOP_TOP + 20])], { size: 0.5 }));
  }

  // Four legs
  for (const [x, y] of byDepth(k.corners({ x: HX - 20, y: HY - 20, w: 40, d: 40, r: 0 }, 0))) {
    out.push(S(k.cylinder(x, y, 3.2, 0, HOP_BOT + 2, P, 20, 0.4), { tone: "mid", crease: "none" }));
    out.push(S(k.cylinder(x, y, 4.6, 0, 1.6, P, 20), { tone: "mid" }));
    out.push(S(k.cylinder(x, y, 4.6, HOP_BOT - 1.6, 1.6, P, 20), { tone: "mid" }));
  }
  // Cross brace
  out.push(S(k.slabOf({ x: HX - 20, y: HY - 1.6, w: 40, d: 3.2, r: 1 }, 12, 3, P, 3, 0.4), { tone: "mid" }));
  return out.join("");
}

function airlock() {
  const out = [];
  const F = G.frameAlong([HX + 12, HY, 17], [0, 1, 0]);
  out.push(S(G.disc(-7, 7, 8, F, P), { tone: "mid" }));
  out.push(L(G.arcOf(F, -7, 8, P, { least: -1 }), { tone: "faint" }));
  out.push(S(G.disc(7, 15, 4.5, F, P), { tone: "mid" }));
  const mb = G.frameAlong([HX + 12, HY - 20, 17], [0, 1, 0]);
  out.push(S(G.disc(-6, 6, 5.5, mb, P), { tone: "mid" }));
  out.push(S(k.slabOf({ x: HX + 6, y: HY - 26, w: 12, d: 12, r: 2 }, 12, 10, P, 4, 0.5), { tone: "mid" }));
  out.push(L(k.knurl(HX + 12, HY - 20, 5.5, 8, 16, 22, P), { tone: "lo" }));
  return out.join("");
}

// ---------------------------------------------------------------------------
// Vault (JDDS)
// ---------------------------------------------------------------------------
function vault() {
  const out = [];
  const VF = G.frameAlong([VX, VY, 0], [0, 0, 1]);
  // Plinth
  out.push(S(k.slabOf({ x: VX - 40, y: VY - 40, w: 80, d: 80, r: 12 }, 0, V_Z, P, 10, 1.0), { tone: "mid" }));
  for (const [x, y] of byDepth(k.corners({ x: VX - 40, y: VY - 40, w: 80, d: 80, r: 12 }, 9))) {
    out.push(S(k.cylinder(x, y, 3, V_Z, 1, P, 18), { tone: "lo" }));
    out.push(DD([at([x, y, V_Z + 1])], { size: 0.45 }));
  }
  out.push(L(k.planOutline(k.insetPlan({ x: VX - 40, y: VY - 40, w: 80, d: 80, r: 12 }, 6), V_Z, P, 10), { tone: "faint" }));

  // Vessel body
  out.push(S(k.cylinder(VX, VY, V_R + 3, V_Z, 4, P, 72), { tone: "hi" }));
  out.push(S(k.cylinder(VX, VY, V_R, V_Z + 4, V_TOP - V_Z - 4, P, 72, 0.8), { tone: "hi", crease: "lo" }));
  // Pressure bands
  for (const z of [V_Z + 18, V_Z + 40, V_Z + 62]) {
    out.push(S(k.cylinder(VX, VY, V_R + 1.6, z, 3, P, 72), { tone: "mid" }));
    out.push(L(k.sideArc(VX, VY, V_R + 1.6, z, P, 48), { tone: "faint" }));
    out.push(DD([at([VX - V_R - 1.6, VY, z + 1.5]), at([VX + V_R + 1.6, VY, z + 1.5])], { size: 0.4 }));
  }
  out.push(k.fadedSvg(G.ribsOf(VF, V_Z + 6, V_TOP - 6, V_R, 40, P, { fade: [0.06, 0.5] }), { tone: "faint" }));

  // Lid + neck
  out.push(S(k.cylinder(VX, VY, V_R + 4, V_TOP, 4, P, 72, 0.6), { tone: "hi" }));
  const lidDots = G.dotsOf(G.frameAlong([VX, VY, V_TOP + 4], [0, 0, 1]), 0, V_R + 1, 20, P, { all: true });
  out.push(DD(lidDots, { size: 0.42 }));
  out.push(S(k.cylinder(VX, VY, 11, V_TOP + 4, 12, P, 48), { tone: "hi" }));
  out.push(S(k.cylinder(VX, VY, 14, V_TOP + 16, 4, P, 48, 0.5), { tone: "mid" }));
  out.push(L(k.sideArc(VX, VY, 14, V_TOP + 16, P, 40), { tone: "faint" }));

  // Relief valve on the neck
  out.push(S(k.cylinder(VX + 20, VY, 4, V_TOP + 4, 12, P, 28), { tone: "mid" }));
  out.push(S(k.cylinder(VX + 20, VY, 7, V_TOP + 16, 3, P, 28, 0.4), { tone: "mid" }));
  out.push(L(k.knurl(VX + 20, VY, 7, V_TOP + 16, V_TOP + 19, 20, P), { tone: "lo" }));

  // Pressure gauge on top (small dial, faces up)
  const gx = VX - 22, gy = VY, gz = V_TOP + 6;
  out.push(S(k.cylinder(gx, gy, 9, gz, 8, P, 48, 0.6), { tone: "mid" }));
  out.push(L(k.ring(gx, gy, 7.2, gz + 8, P, 48), { tone: "lo" }));
  const gt = k.radialTicks(gx, gy, 6.4, 40, 5, gz + 8, [1.0, 2.2], P);
  out.push(L(gt.minor, { tone: "lo" }), L(gt.major, { tone: "mid" }));
  out.push(L(k.ring(gx, gy, 1.3, gz + 8, P, 16), { tone: "mid" }));
  out.push(S(k.cylinder(gx, gy, 2.4, gz - 5, 5, P, 16), { tone: "mid" }));
  return out.join("");
}

function vaultGaugeNeedle(t) {
  const gx = VX - 22, gy = VY, gz = V_TOP + 14;
  const a = (-0.62 + t * 1.0) * Math.PI;
  return k.lineOnTop(
    [gx - Math.sin(a) * 1.6, gy + Math.cos(a) * 1.6],
    [gx + Math.sin(a) * 5.4, gy - Math.cos(a) * 5.4],
    gz + 0.2,
    P,
  );
}

function sightGlass() {
  const out = [];
  const F = G.frameAlong([SX, SY, S_Z0], [0, 0, 1]);
  // glass tube
  out.push(S(k.cylinder(SX, SY, 3.4, S_Z0, S_Z1 - S_Z0, P, 28), { tone: "mid", crease: "none" }));
  out.push(L(k.sideArc(SX, SY, 3.4, S_Z1 - 4, P, 20), { tone: "faint" }));
  out.push(S(k.cylinder(SX, SY, 4.6, S_Z0 - 4, 4, P, 28), { tone: "mid" }));
  out.push(S(k.cylinder(SX, SY, 4.6, S_Z1, 4, P, 28), { tone: "mid" }));
  // scale strip
  const strip = { x: SX - 10, y: SY + 3.4, w: 6, d: 3, r: 0.6 };
  out.push(S(k.slabOf(strip, S_Z0, S_Z1 - S_Z0, P, 3, 0.3), { tone: "lo", crease: "none" }));
  const tks = k.sideTicks(S_Z0 + 4, S_Z1 - 4, 4, 5, strip.x + strip.w, S_Z1, [1.2, 2.4], P);
  out.push(L(tks.minor, { tone: "lo" }), L(tks.major, { tone: "mid" }));
  // brackets
  out.push(S(k.slabOf({ x: VX + 28, y: SY - 1.6, w: 9, d: 3.2, r: 1 }, S_Z0 - 4, 3, P, 3), { tone: "mid" }));
  out.push(S(k.slabOf({ x: VX + 28, y: SY - 1.6, w: 9, d: 3.2, r: 1 }, S_Z1 + 1, 3, P, 3), { tone: "mid" }));
  return out.join("");
}

// ---------------------------------------------------------------------------
// Transfer line hopper -> vault, and tap vault -> manifold
// ---------------------------------------------------------------------------
function transfer() {
  const hopperToVault = pipe(
    [
      [HX + 12, HY, 12],
      [-40, 0, 12],
      [-40, 0, 72],
      [VX - V_R, 0, 72],
    ],
    3.4,
    { bend: 7, maxLength: 18, bias: 0.4 },
  );
  for (const piece of hopperToVault.pieces) add(piece.svg, piece.mid, 0.4);
  flange([-40, 0, 72], [1, 0, 0], 6.4, 4);
  flange([VX - V_R, 0, 72], [1, 0, 0], 6.4, 4);
  // clamps along the run
  for (const x of [-120, -80, -50]) {
    add(S(k.slabOf({ x: x - 2, y: -3.4, w: 4, d: 6.8, r: 1 }, 12, 2.6, P, 3), { tone: "mid" }), [x, 0, 13], 0.5);
    add(DD([at([x, -3.4, 14.6])], { size: 0.4 }), [x, 0, 13], 0.51);
  }

  // Tap: vault -> manifold header
  const tap = pipe(
    [
      [VX + V_R, 0, 46],
      [MX, 0, 46],
      [MX, 0, M_Z],
    ],
    3.2,
    { bend: 6, maxLength: 14, bias: 0.4 },
  );
  for (const piece of tap.pieces) add(piece.svg, piece.mid, 0.4);
  flange([VX + V_R, 0, 46], [1, 0, 0], 6, 4);

  // Manifold header (along y)
  const header = pipe([[MX, -50, M_Z], [MX, 50, M_Z]], 3.6, { bend: 5, maxLength: 16, bias: 0.4 });
  for (const piece of header.pieces) add(piece.svg, piece.mid, 0.4);
  flange([MX, -50, M_Z], [0, -1, 0], 6.6, 4);
  flange([MX, 50, M_Z], [0, 1, 0], 6.6, 4);

  // Manifold post
  add(S(k.cylinder(MX, 0, 4.5, 0, M_Z - 3, P, 24), { tone: "mid", crease: "none" }), [MX, 0, 20], 0.5);
  add(S(k.cylinder(MX, 0, 6.5, 0, 3, P, 24), { tone: "mid" }), [MX, 0, 1.5], 0.5);
  for (const z of [18, 36]) add(L(k.sideArc(MX, 0, 4.5, z, P, 18), { tone: "faint" }), [MX, 0, z], 0.5);
}

// A gate valve on the header at yv (pipe runs along y).
function valve(yv) {
  const out = [];
  out.push(S(k.slabOf({ x: MX - 7, y: yv - 7, w: 14, d: 14, r: 2.5 }, M_Z - 8, 16, P, 4, 0.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan({ x: MX - 7, y: yv - 7, w: 14, d: 14, r: 2.5 }, 1.6), M_Z + 8, P, 4), { tone: "faint" }));
  for (const dx of [-4.5, 4.5]) out.push(DD([at([MX + dx, yv, M_Z + 8])], { size: 0.4 }));
  out.push(S(k.cylinder(MX, yv, 4, M_Z + 8, 6, P, 24), { tone: "mid" }));
  out.push(S(k.cylinder(MX, yv, 7.5, M_Z + 14, 3, P, 32, 0.4), { tone: "mid" }));
  out.push(L(k.knurl(MX, yv, 7.5, M_Z + 14, M_Z + 17, 24, P), { tone: "lo" }));
  // spokes
  for (let i = 0; i < 3; i++) {
    const a = (i / 3) * Math.PI * 2 + 0.3;
    out.push(L(k.lineOnTop([MX + Math.cos(a) * 1.6, yv + Math.sin(a) * 1.6], [MX + Math.cos(a) * 7, yv + Math.sin(a) * 7], M_Z + 17, P), { tone: "lo" }));
  }
  out.push(DD([at([MX, yv, M_Z + 17])], { size: 0.5 }));
  return out.join("");
}

// Branch from a valve to its instrument.
function branch(yv) {
  const route = pipe(
    [
      [MX, yv, M_Z + 6],
      [96, yv, M_Z + 6],
      [IX, yv, M_Z + 2],
      [IX, yv, INDUST_ZS - 2],
    ],
    2.4,
    { bend: 5, maxLength: 12, bias: 0.45 },
  );
  for (const piece of route.pieces) add(piece.svg, piece.mid, 0.45);
  flange([IX, yv, INDUST_ZS - 2], [0, 0, -1], 4.6, 3);
}

// ---------------------------------------------------------------------------
// Instrument bench
// ---------------------------------------------------------------------------
function bench() {
  const out = [];
  out.push(S(k.slabOf(BENCH, 0, BENCH_TOP, P, 8, 1.0), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(BENCH, 5), BENCH_TOP, P, 8), { tone: "faint" }));
  for (const [x, y] of byDepth(k.corners(BENCH, 7))) {
    out.push(L(k.ring(x, y, 2.2, BENCH_TOP, P, 16), { tone: "lo" }));
    out.push(DD([at([x, y, BENCH_TOP])], { size: 0.45 }));
  }
  // leg columns
  for (const [x, y] of byDepth(k.corners(k.insetPlan(BENCH, 10), 0))) {
    out.push(S(k.cylinder(x, y, 4, 0, BENCH_TOP - 2, P, 20), { tone: "mid", crease: "none" }));
  }
  return out.join("");
}

function dialGauge(cx, cy, top) {
  const out = [];
  const R = 15;
  out.push(S(k.cylinder(cx, cy, R, top, 9, P, 64, 0.8), { tone: "hi", crease: "lo" }));
  out.push(L(k.knurl(cx, cy, R, top + 5.6, top + 9, 72, P, 0.3), { tone: "lo" }));
  out.push(L(k.sideArc(cx, cy, R, top + 5.6, P, 40), { tone: "faint" }));
  out.push(L(k.ring(cx, cy, R - 2, top + 9, P, 64), { tone: "lo" }));
  const ticks = k.radialTicks(cx, cy, R - 3, 50, 5, top + 9, [1.1, 2.4], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(L(k.ring(cx, cy, 1.4, top + 9, P, 16), { tone: "mid" }));
  // crown + lug
  out.push(S(k.slabOf({ x: cx + R - 1, y: cy - 2.4, w: 4, d: 4.8, r: 1.2 }, top + 2, 4, P, 3), { tone: "mid" }));
  out.push(S(k.slabOf({ x: cx + R + 2.6, y: cy - 3.2, w: 2.6, d: 6.4, r: 1.2 }, top + 1.4, 6, P, 3), { tone: "mid" }));
  return out.join("");
}

function needleAt(cx, cy, top, t) {
  const a = (0.72 - t * 1.2) * Math.PI;
  return k.lineOnTop(
    [cx - Math.sin(a) * 2.6, cy + Math.cos(a) * 2.6],
    [cx + Math.sin(a) * 11, cy - Math.cos(a) * 11],
    top + 9 + 0.2,
    P,
  );
}

function plotter(cx, cy, top) {
  const out = [];
  // base
  out.push(S(k.slabOf({ x: cx - 22, y: cy - 11, w: 44, d: 22, r: 2.5 }, top, 5, P, 4, 0.5), { tone: "mid" }));
  // drum along x
  const F = G.frameAlong([cx - 19, cy + 7, top + 11], [1, 0, 0]);
  out.push(S(G.disc(-9, 19, 5, F, P), { tone: "hi" }));
  out.push(L(G.arcOf(F, -9, 5, P, { least: -1 }), { tone: "faint" }));
  out.push(L(G.ribsOf(F, -8, 18, 5, 12, P), { tone: "faint" }));
  out.push(S(G.disc(19, 22, 3, F, P), { tone: "mid" }));
  // pen carriage on a rail above the drum
  out.push(S(k.slabOf({ x: cx - 19, y: cy - 11, w: 38, d: 3, r: 1 }, top + 15, 3, P, 3, 0.4), { tone: "mid" }));
  out.push(S(k.slabOf({ x: cx - 4, y: cy - 12.5, w: 9, d: 6, r: 1.4 }, top + 18, 6, P, 3, 0.4), { tone: "hi", crease: "lo" }));
  out.push(S(k.cylinder(cx + 0.5, cy - 11, 1.6, top + 10, 8, P, 16), { tone: "hi" }));
  for (const dx of [-3, 3]) out.push(DD([at([cx + dx, cy - 9, top + 24])], { size: 0.4 }));
  // feed rollers + paper between
  out.push(S(k.cylinder(cx - 19, cy - 8, 3, top + 5, 5, P, 24), { tone: "mid" }));
  out.push(S(k.cylinder(cx + 19, cy - 8, 3, top + 5, 5, P, 24), { tone: "mid" }));
  return out.join("");
}

function heatmap(cx, cy, top) {
  const out = [];
  out.push(S(k.slabOf({ x: cx - 21, y: cy - 13, w: 42, d: 26, r: 2 }, top, 5, P, 4, 0.5), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan({ x: cx - 21, y: cy - 13, w: 42, d: 26, r: 2 }, 2), top + 5, P, 4), { tone: "faint" }));
  const tones = ["hi", "mid", "lo", "faint", "mid", "hi", "lo", "mid", "hi", "faint", "mid", "lo", "mid", "hi", "mid"];
  let i = 0;
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 5; c++) {
      const p = { x: cx - 18 + c * 7.2, y: cy - 10 + r * 7, w: 6, d: 6, r: 0.8 };
      out.push(S(k.slabOf(p, top + 5, 1.4, P, 3), { tone: tones[i++], crease: "none" }));
    }
  }
  out.push(S(k.cylinder(cx + 18, cy - 10, 2, top + 5, 4, P, 16), { tone: "mid" }));
  return out.join("");
}

function ribbon(cx, cy, top) {
  const out = [];
  out.push(S(k.slabOf({ x: cx - 21, y: cy - 10, w: 42, d: 20, r: 2 }, top, 5, P, 4, 0.5), { tone: "mid" }));
  const strip = { x: cx - 18, y: cy - 7, w: 36, d: 14, r: 1 };
  out.push(S(k.slabOf(strip, top + 5, 0.8, P, 3), { tone: "lo", crease: "none" }));
  const tks = k.topTicks(strip.x + 3, strip.x + strip.w - 3, 4, 5, strip.y + 0.8, top + 5.8, [1.4, 2.6], P);
  out.push(L(tks.minor, { tone: "lo" }), L(tks.major, { tone: "mid" }));
  out.push(DD([at([strip.x + 2, strip.y + 3, top + 5.8]), at([strip.x + strip.w - 2, strip.y + 3, top + 5.8])], { size: 0.42 }));
  // pulsing activity dots
  const grid = k.dotGrid(strip.x + 4, strip.y + 8, 7, 2, 4.4, top + 5.8, P);
  out.push(DD(grid, { size: 0.42, tone: "mid", pulse: true }));
  return out.join("");
}

// ---------------------------------------------------------------------------
// Agent gantry (the Python harness)
// ---------------------------------------------------------------------------
function gantry() {
  const out = [];
  for (const x of [G_L, G_R]) {
    out.push(S(k.cylinder(x, 0, 6, 0, 3, P, 28), { tone: "mid" }));
    out.push(S(k.cylinder(x, 0, 4, 3, G_TOP - 3, P, 24, 0.5), { tone: "mid", crease: "none" }));
    out.push(L([26, 58, 90].map((z) => k.sideArc(x, 0, 4, z, P, 16)).join(""), { tone: "faint" }));
    out.push(S(k.slabOf({ x: x - 7, y: -7, w: 14, d: 14, r: 2.5 }, G_TOP - 12, 12, P, 4, 0.6), { tone: "mid" }));
    out.push(DD([at([x + 3, 0, G_TOP - 1]), at([x - 3, 0, G_TOP - 1])], { size: 0.4 }));
  }
  // beam along x
  out.push(S(k.slabOf({ x: G_L, y: -4, w: G_R - G_L, d: 8, r: 2 }, G_TOP, 6, P, 5, 0.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan({ x: G_L, y: -4, w: G_R - G_L, d: 8, r: 2 }, 1.6), G_TOP + 6, P, 5), { tone: "faint" }));
  // rack teeth under the beam
  for (let x = G_L + 8; x < G_R - 6; x += 7) {
    out.push(L(k.segment([x, -4, G_TOP], [x, -4, G_TOP - 3], P), { tone: "faint" }));
  }
  // junction box on the left post
  out.push(S(k.slabOf({ x: G_L - 9, y: -9, w: 12, d: 18, r: 2 }, 70, 20, P, 4, 0.5), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan({ x: G_L - 9, y: -9, w: 12, d: 18, r: 2 }, 2), 90, P, 4), { tone: "faint" }));
  out.push(DD([at([G_L - 6, -3, 90]), at([G_L - 6, 9, 90])], { size: 0.45 }));
  return out.join("");
}

// The live carriage: drawn once at rest, moved with translateAlong.
function carriage() {
  const out = [];
  out.push(S(k.slabOf({ x: -12, y: -9, w: 24, d: 18, r: 3 }, G_TOP - 4, 12, P, 5, 0.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan({ x: -12, y: -9, w: 24, d: 18, r: 3 }, 2), G_TOP + 8, P, 5), { tone: "faint" }));
  // bushings ride the beam
  for (const dx of [-8, 8]) {
    out.push(S(k.slabOf({ x: dx - 3, y: -5, w: 6, d: 10, r: 1.5 }, G_TOP + 6, 5, P, 3), { tone: "mid" }));
    out.push(DD([at([dx, 0, G_TOP + 11])], { size: 0.4 }));
  }
  // arm reaching down toward the vault
  const armF = G.frameAlong([0, 0, G_TOP - 4], [0, -0.42, -0.9]);
  out.push(S(G.prismOf(armF, [[-3, -3], [3, -3], [3, 3], [-3, 3]], 0, 34, P), { tone: "hi", crease: "lo", lit: true }));
  // wrist + lens (the one lit accent)
  out.push(S(k.cylinder(0, -14, 4.6, 62, 7, P, 28), { tone: "hi", lit: true }));
  out.push(L(k.knurl(0, -14, 4.6, 62, 69, 22, P), { tone: "lo" }));
  out.push(S(k.cylinder(0, -14, 7.5, 58, 4, P, 40, 0.4), { tone: "hi", lit: true }));
  out.push(L(k.ring(0, -14, 7.5, 62, P, 40), { tone: "lo" }));
  out.push(L(k.ring(0, -14, 5.4, 58, P, 32), { tone: "mid" }));
  out.push(S(k.cylinder(0, -14, 5.2, 58.6, 0.6, P, 32), { tone: "hi", lit: true }));
  return out.join("");
}

// ---------------------------------------------------------------------------
// Aurora arc (market regime) - drawn in the back plane
// ---------------------------------------------------------------------------
const auroraAngle = (i, n) => (26 + (128 * i) / (n - 1)) * (Math.PI / 180);
const auroraPoint = (a, r) => [A_C[0] + Math.cos(a) * r, A_C[1], A_C[2] + Math.sin(a) * r];

function aurora() {
  const out = [];
  const n = 26;
  for (let i = 0; i < n; i++) {
    const a = auroraAngle(i, n);
    const t = i / (n - 1);
    const tone = t < 0.4 ? "green" : t > 0.6 ? "red" : "lo";
    const r0 = A_R0 + Math.sin(t * Math.PI) * 5;
    const d = k.segment(auroraPoint(a, r0), auroraPoint(a, r0 + 12), P);
    out.push(L(d, { tone }));
  }
  out.push(
    `<path data-part="auroraMark" class="iso-line" data-tone="lit" d="${k.segment(auroraPoint(auroraAngle(13, 26), A_R0 - 6), auroraPoint(auroraAngle(13, 26), A_R0 + 18), P)}" style="stroke-width:1.6"/>`,
  );
  return out.join("");
}

// ---------------------------------------------------------------------------
// Assemble
// ---------------------------------------------------------------------------
items.push({ key: -1e9, svg: base(), name: "base" });
items.push({ key: k.depthOf([HX, HY, HOP_TOP], P) - 0.5, svg: intake(), name: "intake" });
items.push({ key: k.depthOf([HX + 12, HY, 17], P), svg: airlock(), name: "airlock" });
add(transfer(), [MX, 0, 30], 0);
items.push({ key: k.depthOf([VX, VY, 0], P), svg: vault(), name: "vault" });
items.push({ key: k.depthOf([SX, SY, 40], P), svg: sightGlass(), name: "sight" });
items.push({ key: k.depthOf([MX, 0, 0], P), svg: bench(), name: "bench" });

for (const yv of M_YS) {
  items.push({ key: k.depthOf([MX, yv, M_Z], P) + 0.2, svg: valve(yv), name: "valve" });
  branch(yv);
}

items.push({ key: k.depthOf([G_L, 0, G_TOP], P) - 0.6, svg: gantry(), name: "gantry" });

// instruments
add(dialGauge(IX, M_YS[0], INDUST_ZS), [IX, M_YS[0], INDUST_ZS], 0.2);
add(plotter(IX, M_YS[1], INDUST_ZS), [IX, M_YS[1], INDUST_ZS], 0.2);
add(heatmap(IX, M_YS[2], INDUST_ZS), [IX, M_YS[2], INDUST_ZS], 0.2);
add(ribbon(IX, M_YS[3], INDUST_ZS), [IX, M_YS[3], INDUST_ZS], 0.2);

// moving carriage (rest x = -8) and its lit arm
items.push({
  key: k.depthOf([0, 0, G_TOP], P) + 8,
  svg: `<g data-part="carriage" transform="${k.translateAlong(P, [-8, 0, 0])}">${carriage()}</g>`,
  name: "carriage",
});

// aurora behind everything (very low key), with its live marker
items.push({ key: -1e8, svg: `<g data-part="aurora">${aurora()}</g>`, name: "aurora" });

// live fluid column inside the sight glass (filled by the page each frame)
items.push({ key: k.depthOf([SX, SY, 40], P) + 0.5, svg: `<g data-part="level"></g>`, name: "level" });

items.sort((a, b) => a.key - b.key);
const body = items.map((item) => item.svg).join("");

// Live needle placeholders (drawn by the page each frame)
const needleDial = `<path data-part="needleDial" class="iso-line" data-tone="hi" d="${needleAt(IX, M_YS[0], INDUST_ZS, 0.5)}" style="stroke-width:1.2"/>`;
const needleVault = `<path data-part="needleVault" class="iso-line" data-tone="hi" d="${vaultGaugeNeedle(0.5)}" style="stroke-width:1.1"/>`;

const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "The Eclipse Refinery: an isometric market-data machine. A hopper of scrapers feeds one glass vault through a transfer line; a manifold of valves draws from the vault to a bench of gauges; a gantry carriage with a lit lens samples the vault; an arc behind reports the market regime.",
  body: [body, needleDial, needleVault],
});

// ---------------------------------------------------------------------------
// Live script
// ---------------------------------------------------------------------------
const live = `
const P = ${JSON.stringify(P)};
const M = ${JSON.stringify(MODEL)};
const M_YS = ${JSON.stringify(M_YS)};
const IX = ${IX}, INDUST_ZS = ${INDUST_ZS};
const VX = ${VX}, VY = ${VY}, V_TOP = ${V_TOP};
const SX = ${SX}, SY = ${SY}, S_Z0 = ${S_Z0}, S_Z1 = ${S_Z1};
const A_C = ${JSON.stringify(A_C)}, A_R0 = ${A_R0};
const G_TOP = ${G_TOP}, G_L = ${G_L}, G_R = ${G_R};
const CAR_X0 = -8, CAR_X_MIN = G_L + 12, CAR_X_MAX = G_R - 10;
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const carriage = svg.querySelector('[data-part="carriage"]');
const needleDial = svg.querySelector('[data-part="needleDial"]');
const needleVault = svg.querySelector('[data-part="needleVault"]');
const auroraMark = svg.querySelector('[data-part="auroraMark"]');
const level = svg.querySelector('[data-part="level"]');
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");

const angleAt = (i, n) => (26 + (128 * i) / (n - 1)) * (Math.PI / 180);
const aPoint = (a, r) => [A_C[0] + Math.cos(a) * r, A_C[1], A_C[2] + Math.sin(a) * r];
const dialNeedle = (t) => {
  const a = (0.72 - t * 1.2) * Math.PI;
  return lineOnTop([IX - Math.sin(a) * 2.6, M_YS[0] + Math.cos(a) * 2.6], [IX + Math.sin(a) * 11, M_YS[0] - Math.cos(a) * 11], INDUST_ZS + 9 + 0.2, P);
};
const vaultNeedle = (t) => {
  const gx = VX - 22, gy = VY, gz = V_TOP + 14;
  const a = (-0.62 + t * 1.0) * Math.PI;
  return lineOnTop([gx - Math.sin(a) * 1.6, gy + Math.cos(a) * 1.6], [gx + Math.sin(a) * 5.4, gy - Math.cos(a) * 5.4], gz + 0.2, P);
};
const marketFill = ${marketFill.toString()};
const regimeAt = ${regimeAt.toString()};

let clock = 0, last = 0, frame = 0, visible = false, touring = true, idleTimer = 0;
let car = CAR_X0, carTarget = CAR_X0;
let fill = 0.35, fillTarget = 0.35;
let regime = 0.5, regimeTarget = 0.5;
const stageTarget = [G_L + 14, -14, 40, G_R - 12];

function draw() {
  carriage.setAttribute("transform", translateAlong(P, [car - CAR_X0, 0, 0]));
  needleDial.setAttribute("d", dialNeedle(regime));
  needleVault.setAttribute("d", vaultNeedle(fill));
  const a = angleAt(13, 26) + (regime - 0.5) * (128 * Math.PI) / 180 * 0.5;
  auroraMark.setAttribute("d", segmentRaw(aPoint(a, A_R0 - 6), aPoint(a, A_R0 + 18)));
  const h = (S_Z1 - 6 - S_Z0) * fill;
  const paths = solidSvg(cylinder(SX, SY, 2.3, S_Z0, Math.max(0.2, h), P, 16), { tone: "hi" });
  if (level) level.innerHTML = paths;
  const si = M.stages[Math.floor(clock / 3.4) % M.stages.length];
  const text = si.label + " · " + Math.round(fill * 100) + "% of " + M.markets + " markets";
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuenow", String(Math.round(fill * 100)));
  stage.setAttribute("aria-valuetext", si.label + ", vault " + Math.round(fill * 100) + " percent, regime " + (regime < 0.4 ? "risk-off" : regime > 0.6 ? "risk-on" : "neutral"));
}
function segmentRaw(p0, p1) { return segment(p0, p1, P); }

function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60;
  last = now;
  const calm = still.matches;
  if (touring) {
    clock += dt;
    const si = Math.floor(clock / 3.4) % M.stages.length;
    carTarget = stageTarget[si];
    fillTarget = marketFill(clock);
    regimeTarget = regimeAt(clock);
  }
  const ease = (v, tv, tau) => (calm ? tv : v + (tv - v) * (1 - Math.exp(-dt / tau)));
  car = ease(car, carTarget, 0.5);
  fill = ease(fill, fillTarget, 0.8);
  regime = ease(regime, regimeTarget, 0.6);
  if (Math.abs(car - carTarget) < 0.02) car = carTarget;
  draw();
  const settled = !touring && car === carTarget && fill === fillTarget && regime === regimeTarget;
  frame = visible && !settled ? requestAnimationFrame(tick) : 0;
}
const run = () => { if (!frame && visible) { last = 0; frame = requestAnimationFrame(tick); } };
const steer = (next) => {
  touring = false; carTarget = Math.min(CAR_X_MAX, Math.max(CAR_X_MIN, next));
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => { touring = !still.matches; clock = 0; run(); }, 3600);
  run();
};
new IntersectionObserver((entries) => { visible = entries[entries.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
if (still.matches) touring = false;
stage.addEventListener("pointermove", (event) => {
  const box = svg.getBoundingClientRect();
  const share = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
  steer(CAR_X_MIN + share * (CAR_X_MAX - CAR_X_MIN));
});
stage.addEventListener("pointerleave", () => steer(carTarget));
stage.addEventListener("keydown", (event) => {
  let to = null;
  if (event.key === "ArrowRight" || event.key === "ArrowUp") to = carTarget + 10;
  if (event.key === "ArrowLeft" || event.key === "ArrowDown") to = carTarget - 10;
  if (event.key === "Home") to = CAR_X_MIN;
  if (event.key === "End") to = CAR_X_MAX;
  if (to === null) return;
  event.preventDefault();
  steer(to);
});
draw();
`;

// level group lives inside the svg (added to items above).

const card = k.plateHtml({
  fig: "Fig 1",
  title: "The Eclipse Refinery",
  hint: "Hover the bench to move the agent gantry",
  readout: `ingest · 60% of ${MODEL.markets} markets`,
  keys: [
    { mark: "lit", label: "Agent gantry: samples the vault through the read-only port" },
    { mark: "raised", label: "Glass vault (JDDS): the one local store every screen reads" },
    { mark: "green", label: "Aurora arc: market regime, risk-on to risk-off" },
  ],
  caption:
    "Eclipse ingests feeds once into one glass vault (JDDS, SQLite), then serves them to the terminal through API routes and DataHub topics; the Python agent gantry reads that same vault through a read-only bridge. The scope is 34 markets, a 15-minute price cycle and a 5-minute news cycle.",
  body: `<div class="iso-stage" tabindex="0" role="slider" aria-label="The Eclipse Refinery: arrow keys move the agent gantry along the bench" aria-valuemin="0" aria-valuemax="100" aria-valuenow="60">${svg}</div>`,
});

writeFileSync(
  join(HERE, theme === "light" ? "eclipse-refinery-light.html" : "eclipse-refinery.html"),
  k.pageHtml({ title: "The Eclipse Refinery", theme, body: card, script: kitScript() + live }),
);
console.log("wrote", theme === "light" ? "eclipse-refinery-light.html" : "eclipse-refinery.html");
