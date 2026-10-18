# Produce a video

Turn a request for a video into a REAL rendered MP4 through the video tools:
author a storyboard spec, validate it, review a PNG preview, render a draft,
inspect the frames, render the final file and hand over its Artifact Center
entry.

## When to use it

Use this when the user asks for a video, a clip, a recap, an explainer or a
rendered visual they can play or download. If they want a chart, a table or a
3D figure INSIDE the chat instead, the response blocks for those (chart,
model3d) fit better.

## What renders today

Two project kinds:

- `title_card` — the built-in BlackEclipse title card (10 s, 1920x1080@30,
  dark). Takes no spec.
- `storyboard` — a versioned scene specification you author (schemaVersion 2).
  This is how custom videos are made. Seven scene types:

| type | required | optional | notes |
|---|---|---|---|
| `intro` / `outro` | `title` (<=80) | `subtitle` (<=120) | opening / closing titles |
| `metric` | `title`, `metrics` (1-4) | — | each `{label <=40, value <=20, delta <=12}`; delta `+x%` renders green, `-x%` red |
| `candlestick` | `title`, `symbol` (<=12), `candles` (2-60) | — | each `{o,h,l,c}` with `h >= max(o,c)`, `l <= min(o,c)`; the chart reveals left-to-right |
| `comparison` | `title`, `left`, `right` | `winner` (`left`\|`right`) | each pane `{label <=40, value <=20, detail <=60}`; the winner gets the accent frame |
| `timeline` | `title`, `events` (2-6) | — | each `{label <=48, detail <=80}` on a horizontal axis |
| `quote` | `text` (<=280) | `attribution` (<=80) | pulled quote with a decorative mark |

Common scene keys: `durationSeconds` (1-30, required), `transition`
(`cut` default, or `fade` — a 0.4 s cross-fade with the previous scene).

Storyboards are `format: "landscape"` (1920x1080@30), `theme: "dark"`, and
accept a style accent color (`#RRGGBB`, default the Eclipse blue). 1-12
scenes, total duration must fit 300 seconds. Duration is the SUM of scene
durations; there is no separate total field to disagree with it.

Minimal spec:

```json
{
  "schemaVersion": 2,
  "format": "landscape",
  "scenes": [
    {"type": "intro", "durationSeconds": 3, "title": "BITCOIN TODAY", "subtitle": "A market recap"},
    {"type": "metric", "durationSeconds": 4, "transition": "fade", "title": "Key Metrics",
     "metrics": [{"label": "Price", "value": "68,240", "delta": "+2.4%"}]},
    {"type": "outro", "durationSeconds": 3, "transition": "fade", "title": "BLACK ECLIPSE"}
  ]
}
```

## Honesty about values (non-negotiable)

Spec values are DISPLAY STRINGS that you author. They must come from what the
user said, from this conversation, or from real tool results (market data,
fundamentals) — or be BOUND (next section), which is always preferable for
market figures. Never invent a price, a percent change or a quote — if a
number has not been established, say so or bind it rather than inventing it.

## Bound data — schemaVersion 3 (prefer this for every market figure)

Instead of writing a number, DECLARE where it comes from; the render job
resolves it through the Market Data Gateway at retrieval time, and the video
shows the real figure plus its source line:

- candlestick: `"data": {"symbol": "BTC-USD", "interval": "1d"|"4h"|"1h",
  "count": 2-60}` — used INSTEAD of `candles` (never both).
- metric item / comparison pane: `"source": {"symbol": "BTC-USD", "field":
  "price"|"changePct"|"volume"}` — used INSTEAD of `value` (never both; a
  bound price also derives its `delta` from the 24h change).

Verify bindings before rendering with `video_resolve_data` (no render): it
returns what each figure will show, its provider, retrieval time, units and
freshness. MISSING data fails the render (`DATA_UNAVAILABLE`) — nothing is
invented; STALE data renders with a visible STALE marker and is recorded in
the manifest — tell the user when you deliver a render with stale figures.
The job output, `report.json` and the artifact metadata carry the full
evidence manifest (source, retrieval time, units per figure), and a
source line is rendered into the video itself.

## Procedure

1. `video_capabilities` — confirm `ready` is true and the schema version. If it
   is not ready, say why (worker binary not built, FFmpeg tree missing) and
   stop; do not attempt a render that cannot work.
2. Draft the storyboard from the request: pick scenes, write the copy, collect
   the values. Then `video_create_project` with `kind: "storyboard"` and the
   `spec`. A spec problem is refused with a precise path
   (`scenes[2].metrics[0].label: ...`) — fix it and re-create, or use
   `video_update_project` on an existing project (the revision is bumped).
3. `video_validate_project` — spec problems + environment readiness.
4. `video_preview` — a PNG contact sheet plus one frame per scene, registered
   as image artifacts, with any frame findings (clipped text, missing fonts) in
   the job output. This is the cheap look-before-you-render step: only THEN
   spend render time, and show the user what the video looks like before an
   expensive final.
5. `video_render_draft` — half-resolution, finishes in seconds. Poll
   `video_job_status` until terminal. For bound storyboards the job first
   resolves market data; a transient fetch blip is retried inside the job
   (bounded), and `DATA_UNAVAILABLE` after that means a figure could not be
   sourced — fix or drop that binding, never hand-write the number.
6. `video_inspect` on the completed render. Findings (missing fonts, clipped
   text, invalid frames) fail the job as `INSPECTION_FAILED`; report them.
7. Repair a failed render the BOUNDED way: `video_render_repair` with the
   failed job's `ofJobId` and a revised spec (the revision is bumped and the
   retry is linked to the failure). At most 2 repairs per failure line — past
   that the service refuses with `REPAIR_LIMIT_REACHED`, and the right move is
   to report the diagnostics to the user, not to retry again. A transient
   failure (`DATA_UNAVAILABLE` / `WORKER_UNAVAILABLE`) may be retried once
   without a spec change; a content failure without a change is refused
   (`REPAIR_REQUIRES_CHANGE`) because it would only fail again.
8. When the user wants the deliverable: `video_render_final`. Full resolution,
   registers the MP4 in the Artifact Center. Poll `video_job_status`; the job
   output carries the artifact id on success (and records which draft/preview
   of this revision was reviewed, if any).
9. Hand over the result: artifact id, dimensions, duration — and where the
   user can play or download it. Summarize; do not paste raw JSON.

## Honesty rules (non-negotiable)

- A video exists ONLY when a job is `SUCCEEDED` and you hold its artifact id
  (final) or its output path (draft). Anything else is a failure — say so. A
  preview job never produces a video: it produces images.
- `INSPECTION_FAILED` means the rendered frames had problems; the file is not
  a deliverable. Report the findings.
- `TIMED_OUT` and `CANCELLED` are honest end states. `video_cancel_job` is the
  user's lever for a stuck render.
- Repairs are capped: `REPAIR_LIMIT_REACHED` is a terminal answer — report the
  last diagnostics instead of trying again.
- Render durations are estimates for a desktop CPU: quote ranges, not
  promises.

## Notes

Renders are queued Execution Fabric jobs: they survive a harness restart
(lease recovery), and a repeated identical render is safe. Revising a project
bumps its revision; re-render to see the change — nothing in the application
is rebuilt. Previews are cheap PNGs of the same spec (no video file); a final
render records which preview/draft of its revision was reviewed. Audio tracks
and captions are later phases. The worker's prerequisites (Rust binary, FFmpeg
tree) are documented in `docs/video-pipeline.md`.
