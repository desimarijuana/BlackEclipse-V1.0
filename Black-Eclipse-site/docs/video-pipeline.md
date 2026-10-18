---
title: Video Pipeline — fframes Render Worker
status: Current
last-verified: 2026-10-17
---

# Video Pipeline — fframes Render Worker

**Who this is for:** anyone building the native video capability, or a developer
whose first `cargo build` of the worker fails on Windows.

## What exists today (Phases 1–2 — worker + Fabric job layer)

Two pieces, cleanly separated:

1. **The Rust worker** (`rust/fframes-worker/`) — a minimal binary that renders
   a 10-second animated title card to MP4 with
   [fframes](https://github.com/dmtrKovalenko/fframes), pinned exactly to
   `1.2.0` (with a committed `Cargo.lock`). Phase 1 proved the hard part:
   fframes builds and renders on this Windows/MSVC machine against a
   checksum-verified FFmpeg build, deterministically and fast (300 frames of
   1080p in seconds on the CPU backend). The video itself lives in
   `src/main.rs` (`TitleCard`): dark gradient background, cubic-bezier accent
   bar, title/subtitle/chip fade-slide-ins on the frame clock, a linear 10 s
   progress bar and a fade-to-black outro.

2. **The job layer** (`python/harness/video/`) — projects, draft/final
   renders, frame inspection and artifact registration, executed as queued
   **Execution Fabric** jobs (job type `video` on its own `video` queue, on a
   dedicated worker). Renders are never inline; the Fabric owns durability,
   retries, cancellation and lease recovery. Phase 3 exposes it to the agent:
   ten `video_*` tools on the ONE registry plus the bundled
   `system.video-production` skill. The chat artifact UI is Phase 7.

## Phase 2 — the Fabric job layer

The integration plan's worker operations map onto the service like this:

| Operation | Where | Notes |
|---|---|---|
| `create_project` / `validate_project` | `VideoService` + `VideoProjectStore` | Filesystem-backed minimal projects (`<video-root>/projects/<id>.json`): stable id, name, kind (`title_card` today), free-form spec. Validation = spec problems + environment readiness (binary built, FFmpeg tree present). The versioned storyboard schema is Phase 4. |
| `render_draft` / `render_final` | `VideoService` → Fabric job | Submits a `video` job (`action=render`, `mode=draft\|final`). |
| `inspect_video` | `VideoService` → Fabric job | Inspects a completed render by `job_id`, or by `project_id` for its latest successful render. |
| `get_job_status` / `list_jobs` / `cancel_job` | `VideoService` | Reads/operates on the Fabric job records. |
| `get_artifact` | `VideoService` → Artifact Center | The final render's MP4, registered with `source_type=job`, tags `["video","fframes"]` and video metadata (dimensions, frames, duration, inspection summary). |

**What one render job does** (`VideoService.run_render_job`):

1. Resolve and validate the project — an unknown id is a structured failure,
   never a guessed render.
2. Render with the Rust worker as a fixed-argv child process
   (`fframes-worker render --json [--draft] -o <path>`), streaming the
   worker's JSON progress events into Fabric progress (`frame N/M`) and
   killing the child on cancellation.
3. **Inspection gate** — `fframes-worker inspect --json` runs on the produced
   file. Findings (missing fonts, clipped text, invalid SVG) fail the job with
   `INSPECTION_FAILED`; the MP4 stays on disk and referenced in `report.json`.
4. **Final renders only**: register the MP4 into the Artifact Center — a
   catalog failure fails the job (`ARTIFACT_REGISTRATION_FAILED`), because the
   user-visible promise is the artifact, not just a file on disk.

Every job writes `report.json` next to its output
(`<video-root>/jobs/<jobId>/`): request, structured result, raw
render/inspection details. A worker exit of 0 is never trusted on its own — a
missing or empty output file is `RENDER_OUTPUT_MISSING`.

**Lifecycle**: `QUEUED → RUNNING → SUCCEEDED | FAILED | CANCELLED | TIMED_OUT`
(mid-flight cancel requests pass through `CANCEL_REQUESTED`). A worker that
dies mid-render leaves an expired lease; Fabric recovery re-queues the job
(within `max_attempts=2`) and a fresh boot re-drives it — renders are
deterministic, so a retry is safe. The worker registers in
`fabric/builtin_workers.py`; its policy lives in `fabric/policies.py`.

**Using it** (Python — the seam the `video_*` tools wrap):

```python
project = service.video.create_project(name="BTC recap", kind="title_card")
handle = await service.video.render_draft(project["id"])   # {"jobId", ...}
job = service.video.get_job(handle["jobId"])               # status/progress
final = await service.video.render_final(project["id"])    # registers the artifact
await service.video.cancel_job(final["jobId"])
```

**Environment** (all optional): `HARNESS_VIDEO_ENABLED`,
`HARNESS_VIDEO_WORKER_BIN`, `HARNESS_VIDEO_FFMPEG_DIR` (falls back to
`FFMPEG_DIR`), `HARNESS_VIDEO_ROOT` (default `<site>/.black-eclipse/video`),
`HARNESS_VIDEO_DRAFT_TIMEOUT_MS` (10 min), `HARNESS_VIDEO_FINAL_TIMEOUT_MS`
(30 min), `HARNESS_VIDEO_INSPECT_TIMEOUT_MS` (5 min),
`HARNESS_VIDEO_MAX_CONCURRENT` (1).

**Tests**: offline runner + service/Fabric suites with a fake worker holding
the same machine contract (`python/tests/test_video_{runner,service,tools}.py`,
`video_fakes.py`) and an opt-in real end-to-end
(`HARNESS_VIDEO_IT=1` → `tests/test_video_real_smoke.py`: real draft, real
final, artifact registered, real inspection, and the full tool workflow).

## Phase 3 — agent tools + the video-production skill

Ten typed tools on the ONE shared `ToolRegistry` (so schema validation,
timeouts, events and the audit trail apply unchanged), registered by
`video/bootstrap.py` and allowlisted for `eclipse-agent` in `agents.py`:

| Tool | What it does |
|---|---|
| `video_capabilities` | Readiness (worker binary, FFmpeg tree) + supported project kinds — the honest first call for any video request. |
| `video_create_project` / `video_list_projects` | Create and list projects (only kind today: `title_card`). |
| `video_validate_project` | Spec problems + environment readiness before any render. |
| `video_render_draft` / `video_render_final` | Queue the draft / final render jobs; the final registers the MP4 in the Artifact Center. |
| `video_inspect` | Queue a frame inspection of a completed render (by job, or a project's latest render). |
| `video_job_status` / `video_list_jobs` / `video_cancel_job` | Track, list and cancel the queued jobs. |

All ten are `permission="read"` / `risk="low"`: they queue Execution-Fabric
jobs and write only into the confined video workspace and the Artifact Center
— the same class as `ml_*` and `document_create`, and deliberately NOT part of
any effectful tuple in `code/policy.py` (an autonomy profile that narrows
those tools never silently widens video access elsewhere).

The bundled skill `system.video-production`
(`python/harness/skills/library/system/video-production/`) is the procedure an
agent follows: capabilities → create → validate → draft → poll → inspect →
final → hand over the artifact id, with the honesty rules (a video exists only
when a job SUCCEEDED; `INSPECTION_FAILED` / `TIMED_OUT` / `CANCELLED` are
reported as such) and the current capability boundary (title card only —
custom storyboards are Phase 4; the agent must say so, never promise them).

**Acceptance (Phase 3)**: the opt-in real smoke `test_real_tool_workflow` runs
the whole workflow through the registered tools against the real worker —
capabilities → create → draft → status → inspect — and passes on this machine.

## Windows build prerequisites (the non-obvious part)

fframes links FFmpeg's libav libraries and generates its FFI bindings with
libclang. On Windows (MSVC target) you need:

1. **Rust**, MSVC toolchain (built and verified with 1.99.0). The machine needs
   a Visual Studio Build Tools installation for the MSVC linker.
2. **FFmpeg 9.0 shared dev build** — BtbN's
   `ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip` from
   [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest)
   (the `latest` tag; its `include/` + `lib/*.lib` form the MSVC-importable dev
   tree, which is exactly what the fframes README prescribes). Point
   `FFMPEG_DIR` at the extracted folder and put `%FFMPEG_DIR%\bin` on `PATH` —
   the DLLs load at **build time** (proc macros) and at **run time**.
3. **libclang** for bindgen (`ffmpeg-sys-fframes` → `bindgen 0.72`). Any
   libclang ≥ 9 works; set `LIBCLANG_PATH` to the folder containing
   `libclang.dll`. Upstream suggests `winget install LLVM.LLVM` (machine-wide,
   needs elevation). On a non-elevated dev box the lighter route is the PyPI
   wheel into a tools dir: `pip install libclang==18.1.1 --target <dir>`, then
   `LIBCLANG_PATH=<dir>\clang\native`. libclang is **build-time only** —
   machines that merely run the worker never need it.

Do **not** enable codec cargo features (`h264`, `aac`, …) on Windows: they
request a from-source FFmpeg build, which the crate does not support on
Windows. Encoders come from the prebuilt FFmpeg (the BtbN build carries
x264/x265/AAC). This dev machine keeps the two tool trees under
`%USERPROFILE%\.black-eclipse-tools\`.

```powershell
$env:FFMPEG_DIR    = "C:\path\to\ffmpeg-n9.0-latest-win64-gpl-shared-9.0"
$env:LIBCLANG_PATH = "C:\path\to\libclang\native"
$env:PATH          = "$env:FFMPEG_DIR\bin;$env:PATH"
```

## Build, render, inspect

```powershell
# from rust/fframes-worker/ — the first build takes minutes, later builds seconds
cargo build --release

# draft (half-res, fastest preset), then inspect before paying for the full render
cargo run --release -- render --draft -o out/draft.mp4
cargo run --release -- inspect                    # exit code 2 when problems are found
cargo run --release -- render -o out/title-card.mp4

# self-review helpers: a labelled contact sheet and individual frames as PNG
cargo run --release -- strip 0s..10s -n 6         # writes strip.png
cargo run --release -- frame 5s                   # writes frames/5s.png
```

`render` / `inspect` / `strip` / `frame` are fframes' own CLI (cargo feature
`cli`); time specs accept frames (`120`), times (`3.2s`), percentages (`50%`)
and ranges (`a..b`). These commands are what an agent will drive in later
phases: a draft, a machine-readable report, then a final render — never a
claim of success without a validated output.

**Acceptance proof (2026-10-17, this machine):** draft: 300 frames in 1.2 s;
full render: 1920x1080@30 in 2.5 s; `inspect`: "no problems found";
ffprobe: `h264 / yuv420p / 1920x1080 / 30 fps / duration 10.000 s` — a valid
MP4, verified visually via `strip.png` and single frames.

## Invariants and honest limits

- **fframes is pinned `=1.2.0`** in `Cargo.toml` and locked in `Cargo.lock`.
  Bump deliberately and re-run the acceptance proof; the API churns.
- **CPU backend only, for now.** The Skia/Vulkan GPU backend (~10x faster) is a
  separate crate; GPU verification is deferred — the CPU backend is already far
  faster than needed (300 frames in ~2.5 s). `vulkan-1.dll` is present on this
  machine, so the fallback question is open, not blocked.
- **Licensing:** fframes is MIT, but the BtbN build linked here is the **GPL**
  variant (x264/x265). Redistribution of the worker binary must account for
  FFmpeg/encoder licenses — revisit when packaging lands (Phase 8).
- **Renders are always queued Fabric jobs** (type `video`, dedicated worker),
  never inline — the job layer is the narrow interface. The renderer still
  executes only its own compiled code; OS-level sandboxing and resource
  ceilings remain Phase 8 work.

## Where this goes next

Phase roadmap (from the integration plan): **2) done** — the Fabric job layer
is live; **3) done** — the `video_*` tools + `system.video-production` skill
are live; **4)** storyboard/project schema + scene library; **5)**
evidence-bound financial data; **6)** automated preview/repair (the inspection
gate exists; repair loops do not); **7)** chat artifact UI; **8)** hardening
and scheduled recaps. Each phase must leave the app working, and none may
present a failed render as a completed video.
