"""Factor Lab HTTP surface — route registration and operator gating."""

from __future__ import annotations

from harness.routers.factors import router

EXPECTED = {
    "/factors/v1/capabilities",
    "/factors/v1/library",
    "/factors/v1/factors",
    "/factors/v1/factors/{factor_id}",
    "/factors/v1/factors/{factor_id}/versions",
    "/factors/v1/validate",
    "/factors/v1/evaluate",
    "/factors/v1/portfolio",
    "/factors/v1/compose",
    "/factors/v1/experiments",
    "/factors/v1/promote",
    "/factors/v1/lineage",
}


def test_expected_routes_registered():
    paths = {route.path for route in router.routes}
    assert EXPECTED <= paths


def test_every_factor_route_is_operator_gated():
    for route in router.routes:
        names = {dep.call.__name__ for dep in route.dependant.dependencies if dep.call is not None}
        assert "require_operator" in names, f"{route.path} is not operator-gated"


def test_mutations_use_post_and_reads_use_get():
    methods = {route.path: set(route.methods) for route in router.routes}
    assert "POST" in methods["/factors/v1/evaluate"]
    assert "POST" in methods["/factors/v1/portfolio"]
    assert "POST" in methods["/factors/v1/promote"]
    assert methods["/factors/v1/library"] == {"GET"}
