---
name: black-eclipse-anatomy
description: Build crafted, highly detailed 3D mechanism models that explain a finance or technical idea as a real physical object — a matching engine, a settlement rig, a risk dial, a cabinet of lots, a rebalancing gantry. Use whenever someone wants an orbitable 3D model, an explanatory figure, an interactive explainer, or a mechanism model that shows how a market mechanism, data path, portfolio process or system works (in Eclipse chat via the `model3d` block / `/anatomy` command, or as a standalone page from the vendored isometric kit).
license: MIT (Anatomy kit — see src/lib/anatomy/NOTICE)
compatibility: Eclipse chat (`anatomy` response block); the vendored kit runs framework-free (Node/TS writing SVG) and in React/Next.js.
metadata:
  opencode/slash: "true"
---

# BlackEclipse Anatomy

Adapted from the MIT-licensed **Anatomy** skill (wheresryan22/anatomy). Its one
idea: **the object is the explanation.** Don't draw boxes, arrows and labels —
invent a real, well-made physical thing whose working *is* the concept, built from
**many small, precise, purposeful parts**. Two failure modes, seen in practice:
too abstract (stacked plates and labelled boxes) and too flat (one slab with a few
lines). Both are fixed the same way: a recognisable machine with real parts.

## Two ways to use it in Eclipse

1. **In chat (default) — the `model3d` block / `/anatomy` command.** The model
   authors a declarative 3D SCENE (JSON) that Eclipse compiles to world-space
   meshes and draws in an orbitable WebGL viewport (frosted card, numbered key,
   legend, live readout, step-through stages, `.glb` download). No
   model-authored meshes, SVG or code. This is the finance path.
2. **Standalone figure — the vendored kit.** For docs, blog posts or a landing
   page, build a page from the kit under `docs/figures/eclipse-refinery/`
   (`kit/iso-kit.mjs`, `kit/lathe.mjs` for round parts, `kit/tube.mjs` for pipes
   and cables, `kit/gl.mjs` for WebGL, `kit/audit.mjs` to prove the geometry) —
   the upstream craft workflow, `node examples/<name>/build.mjs`.

The legacy isometric `anatomy` block (compiled by `src/lib/anatomy/scene.ts`) is
still supported for older payloads, but new figures use `model3d`.

## In-chat scene (what the `model3d` block accepts)

Give the compile a real machine. Field names are exact — read them live with
`response_block_schema` (never guess).

- `parts[]`, each: `id`, an optional `parent`, a transform (`position`,
  `rotation` in degrees, `scale`), `material`/`tone`/`lit`/`label`, and geometry
  as either a **`recipe`** (+ numeric `params`) or a **`kind`**.
  - `kind`: `box` · `cylinder` · `cone` · `sphere` · `torus` · `lathe` (a
    `profile` of `[z, radius]` pairs) · `extrude` (a `points` polygon) · `tube`
    (a `path` of `[x,y,z]`) · `gear` (`teeth`/`toothDepth`).
  - `recipe` (PREFER these — they expand into detailed assemblies): `motor` ·
    `gearbox` · `pump` · `valve` · `gauge` · `tank` · `bearing` · `gear` ·
    `pulley` · `belt-drive` · `frame` · `bracket` · `fan` · `heat-exchanger` ·
    `pcb` · `lever` · `spring`. A recipe node takes `params` (numbers) plus the
    same transform.
  - `tone`: the shared status vocabulary `neutral|info|success|warning|danger`
    (it colours the part and its wires). `material`: `metal|paint|rubber|glass|
    plastic|emissive`.
- `wires[]`: `from`/`to` part ids, optional `dashed`/`dotted`, `tone`.
- `legend[]`: `{ label, mark }`.
- `stages[]`: `{ label, note, readout, lit }` — the deterministic tour. `lit` is
  a boolean or an id list; `readout` is the ONLY source of live text, so it must
  be true (never an invented number).
- `camera`: `azimuth` (default 45), `elevation` (default 28), `distance`.
  Coordinates are world units, z up (0 = ground); the scene is dropped onto the
  ground automatically.

**Compose, don't pile:** 8–30 nodes from recipes + primitives reads as a machine.

## Craft rules (finance flavour)

- **The object is the explanation.** Map the concept to a machine:
  matching engine → a drum/platen that pairs tickets; order book → a stack of
  drawers each as deep as its depth; settlement T+2 → a two-belt rig where the
  cash belt and the securities belt only meet at a gauge on the settlement date;
  rebalancing → a gantry that measures drift and moves weights past a band;
  FIFO cost basis → a rack of dated trays consumed front-to-back; option greeks →
  a dial gauge per sensitivity on one shaft; a risk engine → a bank of valves and
  gauges fed by one manifold.
- **Many small parts, each on another.** Base plate on feet with corner screws and
  a ruler strip (`ticks`), posts/rails, the moving mechanism, a knurled control
  (`knob`+`knurl`), and exactly one lit subject (`lit: true`, `halo: true`).
- **Real numbers and behaviour.** The readout, motion and caption must be true.
  Ground every figure in the mechanism's real steps; if a figure needs a value the
  run did not produce, leave it out — never invent it.
- **A numbered key, not floating labels.** Each part's `label` is a full sentence;
  it is listed in a numbered key under the figure (SVG text cannot wrap).
- **Tone hierarchy.** base/structure neutral; the subject or the flow the reader
  should watch gets `success`/`info`; a caution gets `warning`; a stop gets
  `danger`. Colour is meaning, not decoration.
- **Calm.** Stages step; autoplay is opt-in and off under reduced motion.

## Finance example prompts

- `/anatomy how a limit order becomes a trade in a matching engine`
- `/anatomy the BlackEclipse market-data path from provider feed to JDdS to the agent --animated`
- `/anatomy how a portfolio rebalance decides what to buy and sell when a holding drifts past its target weight --animated`
- `/anatomy how a trade settles by T+2 --animated`
- `/anatomy how a FIFO cost-basis lot is opened and closed as buys and sells settle`
- `/anatomy how the fiduciary gate verifies an advisory claim before the answer is sent`

## Standalone figures (the vendored kit)

For a figure that ships as a page or a `.svg`, follow the upstream workflow: size
it (Figure 40–80 parts, Hero 80–150), collect the true numbers, invent the object,
write the parts list, plan the world (x/y floor, z up), build geometry once with
the kit, paint back to front, frame it (`Fig n`, title, hint, live readout), make
it live with calm eased motion, and verify by reading your own PNGs and running
the audits (`node build.mjs --audit`, `node scripts/lines.mjs`). Full craft notes
live with the kit: `docs/figures/eclipse-refinery/` and the upstream references.
