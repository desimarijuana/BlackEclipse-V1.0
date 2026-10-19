# Interactive 3D Anatomy Model

Explain how a system, machine or process works as an interactive **3D model** —
an orbitable machine of many small parts, with a numbered key, a legend, a live
readout and step-through stages — rendered inline in the chat as a `model3d`
block.

## When to use it

Use this when the user wants to understand **how something works** — a matching
engine, the JDdS data path, a rebalancing loop, a settlement rig, a risk engine,
an option's greeks — and a picture explains it better than prose. Not for charts
or tables (those are their own blocks). The `/anatomy <concept>` slash command
routes here.

## The one idea

**The object is the explanation.** Invent a real, well-made physical thing whose
working *is* the concept. Build it from **reusable mechanism recipes** rather
than hand-placed primitives: `motor`, `gearbox`, `pump`, `valve`, `gauge`,
`tank`, `bearing`, `gear`, `pulley`, `belt-drive`, `frame`, `bracket`, `fan`,
`heat-exchanger`, `pcb`, `lever`, `spring`. A recipe expands into a detailed
assembly; composing 8–30 nodes from recipes is what makes the model read as a
machine instead of "a pile of cylinders".

Finance mappings: matching engine → a `gearbox` whose gear pairs tickets; order
book → a `frame` of drawers each as deep as its depth; T+2 settlement → a
`belt-drive` where the cash belt and securities belt only meet at a `gauge`;
FIFO cost basis → a `frame` of dated `tank`s consumed front-to-back.

## Procedure

1. State the mechanism in one sentence and confirm the audience if it matters.
2. Call `response_block_schema` for the `model3d` block and use its EXACT field
   names — a drifted field degrades the model.
3. Author a SCENE, never meshes, shaders or code:
   - `parts[]` — `id`, a `position`/`rotation`/`scale`, an optional `parent`
     (for assemblies), `material`/`tone`/`lit`/`label`, and geometry: either a
     `recipe` (+ numeric `params`) or a `kind`.
     - KINDS: `box` · `cylinder` · `cone` · `sphere` · `torus` · `lathe` (a
       `profile` of `[z, radius]` pairs) · `extrude` (a `points` polygon) ·
       `tube` (a `path` of `[x,y,z]`) · `gear` (`teeth`/`toothDepth`).
     - RECIPES: `motor` · `gearbox` · `pump` · `valve` · `gauge` · `tank` ·
       `bearing` · `gear` · `pulley` · `belt-drive` · `frame` · `bracket` ·
       `fan` · `heat-exchanger` · `pcb` · `lever` · `spring`.
   - `wires[]` between part ids (`from`/`to`, `tone`, optional `dashed`).
   - a `legend[]`, a short `description`, an optional `camera`
     (`azimuth`/`elevation`/`distance`), and `stages[]` (`label`, `note`,
     `readout`, `lit`) for the step-through.
   - Coordinates are world units, z up (0 = ground). The whole scene is dropped
     onto the ground automatically, so build parts above z = 0.
4. Give each node a short id and a descriptive label; the label is listed in a
   numbered key under the model (a full sentence is fine). Clicking a key selects
   and highlights that part on the model (and clicking a part selects its key).
   Do not claim hover/inspection the model does not have.
5. Emit ONE ```eclipse-response fence containing a single `model3d` block, then a
   short explanation. Use only a recipe's real parameter keys — an unknown key is
   silently ignored by the schema, so a misspelling renders a different part
   instead of raising an error. Keep every label and readout true; never invent a
   component, a recipe or a value. Do not repeat the model's content as a list.

## Notes

This routine is a **draft**. The model is a declarative scene the model authors —
never meshes, HTML or code. It can be orbited, zoomed and downloaded as a `.glb`.
The legacy isometric `anatomy` block still renders for older payloads; new work
should use `model3d`. For a standalone page or `.svg`, the full Anatomy kit is
vendored for reference under `docs/figures/eclipse-refinery/`.
