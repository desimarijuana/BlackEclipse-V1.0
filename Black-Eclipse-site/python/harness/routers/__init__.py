"""Route routers for the harness runtime.

Each router owns one coherent route group and reaches the shared runtime state
through `harness.deps` (never by importing `main`). Routers are registered by
`main` with `app.include_router(...)`.
"""
