# BlackEclipse harness launch video script

**Format:** 30 seconds, 1920×1080, 30 fps, HyperFrames

**Core idea:** Eclipse turns one plain-language request into a bounded,
observable work session. Viewers see what they can actually use it for:
research a market move, run a chosen bot, apply a skill, build a workflow,
produce a chart, and inspect the evidence behind the answer.

**Production rule:** Use real captures from the installed Black Eclipse desktop
app at `%LOCALAPPDATA%\Programs\BlackEclipse\Black Eclipse.exe`.
Do not recreate product UI from memory. If a surface is not capturable, label it
on screen as `SCREENSHOT NEEDED: <surface>` rather than drawing an invented panel.

## Voice and sound

No voiceover. Use short kinetic titles and the product's real labels. Use a
restrained electronic pulse, cursor clicks, graph-node snaps, a tool-call tick,
and one low impact when the evidence view lands.

## Shot-by-shot script

| Time | Picture / action | On-screen copy | Sound |
|---|---|---|---|
| 0:00–0:03 | Open on the real Eclipse desktop app with a live market surface. The cursor enters: `Why did AMD move today? Compare the evidence and chart it.` | `Ask a real question.` | Pulse starts; keyboard taps |
| 0:03–0:06 | Open the real `+` menu. Show the available mode controls and select the relevant mode, preserving the actual labels and selected state. | `Pick the mode for the job.` | Menu click; mode-lock tick |
| 0:06–0:10 | Show the real bot/agent preset surface. Choose a research, market-data, valuation, risk, or other available preset; isolate its role, tool allowlist, and limits. | `Choose a bot with a job to do.` | Preset click; low rise |
| 0:10–0:14 | Start the run. Punch into the real event stream as the harness calls tools, returns market data, and records source/provenance state. | `The harness turns intent into steps.` | Tool-call ticks; result chime |
| 0:14–0:17 | Show a real skill being found or invoked. Keep the skill name and trust/status visible; show that skills add procedure without bypassing permissions. | `Use skills without losing control.` | Lock click |
| 0:17–0:21 | Enter Graph Studio. Show the actual canvas changing from request → agent/tool node → data node → chart/output node. Highlight the node configuration rather than presenting a decorative diagram. | `Build repeatable work as a graph.` | Node snaps in rhythm |
| 0:21–0:24 | Execute the workflow and show its real run state moving through nodes. If test mode is available, keep its label visible so viewers understand the boundary. | `Run it. Inspect every step.` | Branch split; measured pulse |
| 0:24–0:27 | Pull back to the resulting chart or graph. Show the real symbol, axes, comparison/indicator, timestamp or freshness label, and the final answer/artifact reference. | `Turn research into something you can use.` | Chart trace draws; impact |
| 0:27–0:30 | Open run detail for a final glimpse of events, tools, sources, and outcome. Return to the full workspace; mark lands once with the CTA. | `BlackEclipse`  \n`Research. Automate. See the proof.`  \n`Run the work. Keep the trail.` | Final mark hit; hold |

## Capture checklist

Capture these states from the installed app before animating the film. The
same request should travel through as many shots as possible so the viewer can
follow cause → run → result:

1. Full workspace with sidebar, composer, top-level navigation, and a real
   market/chart surface.
2. Composer `+` menu with the actual mode labels and selected state.
3. Bot/agent preset surface with the real preset name, task role, tool boundary,
   model/provider pin if exposed, and run limits.
4. A live or completed run showing the request, tool events, source/provenance
   labels, intermediate output, and terminal status.
5. Skills surface showing a real skill name, status/trust state, permission
   boundary, and invocation
   or detail view.
6. Graph Studio canvas with one real workflow and its configuration panel:
   agent, tools, memory scope, branching, and output shape where available.
7. Graph run result with a real output/chart node and a visible run status.
8. Observability/run-detail view with trace, events, tool history, and metrics
   such as latency or cost only when the app exposes them.
9. The real BlackEclipse mark and wordmark from the app assets.

## Claims to avoid

- Do not say a bot is autonomous, unrestricted, or always correct.
- Do not claim a specific speed, accuracy, market count, or cost unless that
  exact value is visible in the captured app state.
- Do not imply that charts, skills, or MCP tools bypass the harness permission
  and provenance boundaries.
- Do not show fabricated finance values. Use the app's live value, a clearly
  labeled simulation, or `UNAVAILABLE`.

## Editorial notes

This script is intentionally a feature journey, not a list of cards: one
question travels through mode selection, bot execution, skills, Graph Studio,
charts, and observability before returning to the workspace. The emphasis is
use-case clarity: Eclipse is for turning research, analysis, and repeatable
agent work into inspectable runs and reusable workflows.
