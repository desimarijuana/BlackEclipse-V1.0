---
title: Graph Studio — Node Legibility & Usability Plan
status: Proposed
last-verified: 2026-11-01
---

# Node legibility & usability plan

**The problem in one sentence:** the nodes are capable but not *legible* — a
person cannot tell, from the canvas alone, what a node does, which connector is
which, or where a value should go.

Concrete evidence from real use:

- **If / else shows three connectors.** Two are control (`true`/`false`), one is
  a boolean (`result`). They render as identical dots with the name hidden in a
  hover tooltip, so there is no way to know which is the "if" branch.
- **Switch still shows ten connectors** in the inspector even after the card
  learned to hide unconfigured cases — the inspector lists the raw declaration.
- **Port names are invisible.** Every handle is an anonymous 10 px dot; names
  live only in `title` tooltips.
- **"What does this node do?"** is a `description` string shown only in the
  palette and inspector, never where the node is read.
- **Every node looks the same.** Control ports and data ports are visually
  identical, so a branch handle and a value handle cannot be told apart.

This is not a contract problem. It is a **surface** problem, and it is fixable
without changing what any node does.

## 0. Progress

| Item | Status |
| --- | --- |
| U1.1 visible port labels | **done** — outputs right, inputs left, chip background, single ports keep the dot |
| U1.2 control/square vs data/round | **done** — card + inspector + legend |
| U1.3 branch-first order, `caseIndex` only when wired | **done** |
| U1.4 human port names (`If true`/`If false`/`No match`/`Any match`) | **done** — both registries + manifest |
| U1.5 inspector uses the same visible ports | **done** |
| U1.6 validation names the human label | **done** (messages use `port.name`) |
| U2.1 node description as the card subtitle | **done** |
| U2.2 inspector header shows the description | **done** |
| U2.3 palette shows `in`/`out` counts + a `branch` marker | **done** |
| U2.4 insertion preview explains the chosen port | **done** — names the port and why the list is filtered |
| U3.1 unwired required inputs flagged on the card | **done** — amber ring, "Connect: Items", tooltip |
| U3.2 "branch fired into nothing" run event | **done** — `executor._report_dead_branch` |
| U3.3 `matched` + `caseN` both wired warning | **done** — `switch_double_branch` |
| U3.4 first-run tour | **done** — 3-card `GraphOnboarding`, once per browser, dismissible; the same content stays in the `?` panel |
| U4 reduce port surface | **deferred by decision** — presentation already hides unused ports; variadic ports need manifest v2 + validator + executor + canvas, and buy nothing a user can see yet. Revisit when a graph needs > 8 cases or > 3 merge inputs. |
| U5.1 worked examples | **done** — `node-examples.ts`, inspector Example block |
| U5.2 labelled diagram | **done** — `docs/graph-studio.md` "Reading a node" |


---

## 1. What n8n does that we should copy

| # | n8n behaviour | Why it works | Our gap |
| --- | --- | --- | --- |
| 1 | **Output labels are visible** next to the connector (`true`, `false`, `done`) | You drag from a *named* branch, not a dot | Names are tooltip-only |
| 2 | **IF/Switch have dedicated branch outputs** with text labels, and one optional data output | The node reads like the sentence it implements | Yes — but unlabelled |
| 3 | **One input by default; extra inputs are explicit** | Fewer choices, no guessing | We expose every declared port |
| 4 | **Colour/shape by role** (trigger, action, branch) | Category is readable at a glance | All handles look identical |
| 5 | **The node's subtitle says what it does** ("Route items into two branches") | Answers "what is this?" on the canvas | Hidden in tooltip/inspector |
| 6 | **The parameter panel explains each field** with help text and expected shape | You can configure without docs | We have `help`, but ports are unexplained |
| 7 | **Empty inputs are visibly empty** ("connect a value") | The next action is obvious | A dot with no meaning |

We already have (2) and (6) partially; the plan is mostly about (1), (3), (4),
(5) and (7).

---

## 2. Surfaces that must agree

Ports and node meaning are rendered in **six** places. Any fix must cover all of
them, or the app contradicts itself.

| Surface | File | Today |
| --- | --- | --- |
| Canvas node card (handles) | `eclipse-node.tsx` | anonymous dots, fanned, tooltip only |
| Canvas node card (body) | `eclipse-node.tsx` | icon + label + up to two inline fields |
| Inspector · Settings | `node-inspector.tsx` | raw `def.inputs` / `def.outputs` list |
| Inspector · Parameters | `node-inspector.tsx` + `config-field.tsx` | field help exists |
| Palette | `node-search-panel.tsx` | name + description |
| Validation / run errors | `validation.ts`, `run-panel.tsx` | names the node id, not the port label |

---

## 3. Design decisions (the rules everything follows)

1. **A connector always has a visible label when it is not alone.** Single-port
   nodes keep the dot only. Labels sit outside the card, right of outputs and
   left of inputs, on a translucent chip so an edge cannot hide them.
2. **Control ports look different from data ports.** Control = square, accent
   filled; data = round, type-coloured. A branch can never be mistaken for a value.
3. **Branch outputs come first**, in the order a person says them ("If true",
   "If false", then "Result").
4. **Secondary outputs are hidden until used.** `caseIndex` is inspection data,
   not a branch; it appears on the card only when something is wired to it.
   Configured cases decide how many `caseN` handles exist (already shipped).
5. **Names are the sentence, not the schema.** `true` → **If true**,
   `false` → **If false**, `default` → **No match**, `matched` → **Any match**.
   Handles keep their ids, so saved graphs are untouched.
6. **Every node states what it does in one line**, on the card (subtitle) and at
   the top of the inspector. `description` is already written for every node —
   surface it.
7. **An unconnected required input says so.** The card marks it and the inspector
   shows "connect a value or set a literal".

---

## 4. Workstreams

### U1 — Port legibility (the fix people will notice)

| ID | Task | Files | Effort |
| --- | --- | --- | --- |
| U1.1 | Visible port labels (outputs right, inputs left; chip; hidden when alone) | `eclipse-node.tsx` | M |
| U1.2 | Control = square, data = round; legend in the help panel | `eclipse-node.tsx` | S |
| U1.3 | Branch-first port order + `caseIndex` only when wired | `node-ports.ts` | S |
| U1.4 | Rename `true`/`false`/`default` to human labels in **both** registries + manifest | `registry.ts`, `nodes.py`, regenerate | S |
| U1.5 | Inspector Settings uses `visiblePorts` and marks Control/Data | `node-inspector.tsx` | S |
| U1.6 | Port labels in validation messages (`true` → "If true") | `validation.ts` | S |

**Acceptance:** with the canvas at 100 % zoom and no hovering, a person can point
at an If/else node and say which connector is the "if" branch, which is "else",
and which carries the boolean.

### U2 — Node meaning on the canvas

| ID | Task | Files |
| --- | --- | --- |
| U2.1 | One-line description under the node title (truncated, full text in tooltip) | `eclipse-node.tsx` |
| U2.2 | Inspector header: description + docs string + category chip | `node-inspector.tsx` |
| U2.3 | Palette: show input/output count and a control-branch marker | `node-search-panel.tsx` |
| U2.4 | "Add node" insertion preview explains what the chosen port does | `node-search-panel.tsx` |

### U3 — Guided mistakes

| ID | Task |
| --- | --- |
| U3.1 | Mark unwired required inputs on the card (small amber ring + "connect") |
| U3.2 | When a control output fires but nothing is wired, show a run event ("N did nothing — its branch is unwired") |
| U3.3 | When `matched` **and** a `caseN` are both wired, warn that both branches will run |
| U3.4 | First-run tour on a new canvas (3 steps: what a node is, how ports work, how to run) |

### U4 — Reduce the port surface (contract work)

| ID | Task |
| --- | --- |
| U4.1 | Merge `matched` into… nothing: keep it, but default it to hidden unless wired, once `caseN` exists (needs a saved-graph check) |
| U4.2 | Give `logic.condition` a single `choose`-style output? **No** — two labelled branches is the n8n model and it is clearer. Decided. |
| U4.3 | Variadic ports (E6 of the logic plan) so a merge/switch never over-declares |

### U5 — Documentation that lives where the user is

| ID | Task |
| --- | --- |
| U5.1 | A per-node "examples" line in the inspector (input → output) |
| U5.2 | `docs/graph-studio.md` gets a "reading a node" section with a labelled diagram |

---

## 5. Per-node labelling spec

Rules 5 and 6 applied to every node. Only the rows that change are listed;
everything else keeps its current name.

| Node | Inputs | Outputs | One-liner (card subtitle) |
| --- | --- | --- | --- |
| `logic.condition` | Value | **If true**, **If false**, Result | Routes the run down one of two branches |
| `logic.switch` | Value | each case value, **No match**, **Any match**, (Case index) | Sends a value to the branch that matches |
| `flow.gate` | Run, Run 2, Run 3, Value | Value, Done | Only lets the run through when its branch fired |
| `logic.merge` | Run, A, B | Value, Done | Takes the first branch that produced something |
| `logic.map` | Run, Items | Items, Done | Transforms every item with a formula |
| `logic.filter` | Run, Items | Items, Dropped, Done | Keeps only the items that pass a test |
| `logic.reduce` | Run, Items | Value, Done | Folds a list into one number |
| `logic.aggregate` | Run, Items | Value, Groups, Done | Groups rows and computes a statistic |
| `logic.deduplicate` | Run, Items | Items, Dropped, Done | Removes duplicate rows |
| `logic.wait` | Run | Waited, Done | Pauses for a set time |
| `logic.stop` | Run, Output | Stopped | Ends the run here with a status |
| `flow.repeat` | Run, Input | State, Iterations, Stopped, Done | Runs the body a fixed number of times |
| `flow.while` | Run, Input | State, Iterations, Stopped, Done | Runs the body while a condition holds |
| `flow.for_each` | Run, Items | Results, Iterations, Stopped, Done | Runs the body once per item |
| `flow.subworkflow` | Input | Output, Run id | Runs another saved workflow |
| trigger/data/transform/output | unchanged | unchanged | unchanged |

---

## 6. What "done" looks like

A new user, with no docs, can answer these in under ten seconds per node:

1. **What does this node do?** — reads it on the card.
2. **Where does my value go?** — the input label says so.
3. **Which connector is the branch?** — square, labelled, branch-first.
4. **Why did nothing happen?** — the unwired branch is flagged in the run log.
5. **Do I have to configure it?** — the inspector marks required fields and
   shows the node's expected shape.

---

## 7. Sequencing

U1 is one focused change set and removes the reported pain. U2 + U3 follow.
U4 is contract work and is only worth doing with Wave 2 of the logic plan.
