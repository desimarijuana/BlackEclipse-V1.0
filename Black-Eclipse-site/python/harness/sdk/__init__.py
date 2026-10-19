"""Eclipse SDK — the user-facing extension surface.

Submodules are imported directly (`harness.sdk.locks`, `harness.sdk.service`, …)
so this package init stays dependency-free. In particular, `ui/service.py` and
`portfolio/service.py` import `sdk.locks` lazily for enforcement; an eager
package init would pull the UI/Portfolio services back in and risk a cycle.
"""
