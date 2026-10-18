# Produce a video

Turn a request for a video into a REAL rendered MP4 through the video tools:
create and validate a project, render a draft, inspect the frames, render the
final file and hand over its Artifact Center entry.

## When to use it

Use this when the user asks for a video, a clip, an animated title, an opener
or a rendered visual they can play or download. If they want a chart, a table
or a 3D figure INSIDE the chat instead, the response blocks for those (chart,
model3d) fit better.

## What actually renders today (read this first)

The pipeline has exactly ONE project kind: `title_card` — the built-in
BlackEclipse title card (10 seconds, 1920x1080 at 30 fps, dark theme, animated
accent bar, subtitle line, progress bar, fade-out).

- If the request IS the title card (branding, opener, "the BlackEclipse
  intro"), proceed to the procedure.
- If the user wants custom scenes, candlesticks, voiceover or data-bound
  footage, be TRANSPARENT: that is not implemented yet. Offer the title card,
  or the in-chat chart/anatomy blocks. Never promise a custom video, and never
  claim one exists.

## Procedure

1. `video_capabilities` — confirm `ready` is true. If it is not, say why
   (worker binary not built, FFmpeg tree missing) and stop; do not attempt a
   render that cannot work.
2. `video_create_project` with a name taken from the user's brief (kind
   `title_card`, the only supported kind).
3. `video_validate_project` — fix anything it reports. A project with problems
   is refused by the renderer, so do not submit one.
4. `video_render_draft` — returns a job id. Drafts are half-resolution and
   finish in seconds.
5. `video_job_status` until the job is terminal. `RUNNING` reports frame
   progress; `QUEUED` waits for the queue slot.
6. `video_inspect` on the completed render. Problems (missing fonts, clipped
   text, invalid frames) fail the job as `INSPECTION_FAILED`; report what was
   found instead of pretending the file is a deliverable.
7. When the user wants the deliverable (or asked for the video outright):
   `video_render_final`. Final renders are full resolution, take minutes on
   the CPU backend, and REGISTER the MP4 in the Artifact Center. Poll
   `video_job_status`; the job output carries the artifact id on success.
8. Hand over the result: the artifact id, the file's dimensions and duration,
   and where the user can play or download it. Summarize the job — do not
   paste raw JSON.

## Honesty rules (non-negotiable)

- A video exists ONLY when a job is `SUCCEEDED` and you hold its artifact id
  (final) or its output path (draft). Anything else is a failure — say so.
- `INSPECTION_FAILED` means the rendered frames had problems; the file is not
  a deliverable. Report the findings.
- `TIMED_OUT` and `CANCELLED` are honest end states. `video_cancel_job` is the
  user's lever for a stuck render.
- Render durations are estimates for a desktop CPU: quote ranges, not
  promises.

## Notes

Renders are queued Execution Fabric jobs: they survive a harness restart
(lease recovery) and a repeated identical render is safe. Storyboards, custom
scenes and data-bound charts are the next phase — this routine grows with
them. The worker's prerequisites (Rust binary, FFmpeg tree) are documented in
`docs/video-pipeline.md`.
