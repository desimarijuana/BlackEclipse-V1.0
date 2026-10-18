# rust/ — native workers

The native video render worker lives in [`fframes-worker/`](./fframes-worker):
an [fframes](https://github.com/dmtrKovalenko/fframes) (Rust) renderer that
compiles video projects to MP4 in its own process.

**Read first:** [`docs/video-pipeline.md`](../docs/video-pipeline.md) — purpose,
current phase, the Windows build prerequisites (FFmpeg 9 dev build + libclang),
build/render/inspect commands, and the version-pinning policy.
