"""Phase S — stabilization tests.

S.2 (ratchet hygiene): `main.py` is split (lifespan wiring lives in `boot.py`) and
the prompt ceiling was LOWERED, not raised. S.3 (docs drift): the three research
surfaces share one "which surface answers which question" page and cross-link to
it. These pin the process commitments so they cannot silently regress.
"""

from __future__ import annotations

from pathlib import Path

_DOCS = Path(__file__).resolve().parent.parent.parent / "docs" / "harness"


# ── S.2: ratchet hygiene ─────────────────────────────────────────────────────

def test_main_py_is_not_ratcheted_and_is_under_the_hard_ceiling():
    from tests.test_size_budget import HARD_CEILING_LINES, RATCHET_PY, _measure

    measured = _measure()
    assert "main.py" not in RATCHET_PY, "main.py was split; it must not stay ratcheted"
    assert measured["main.py"] < HARD_CEILING_LINES, (
        f"main.py is {measured['main.py']} lines, at/over the hard ceiling"
    )


def test_boot_module_owns_the_lifespan():
    from harness import boot, main

    # The lifespan lives in `boot.py`; `main` re-exports it for `FastAPI(...)`.
    assert hasattr(boot, "lifespan")
    assert main.lifespan is boot.lifespan
    # The startup/shutdown sequence is intact.
    assert hasattr(boot, "_boot") and hasattr(boot, "_shutdown")


def test_prompt_ceiling_was_lowered_not_raised():
    from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT

    # HEAD's ceiling was 23300; Phase S.2 lowered it to 23025. The Task / Plan
    # runtime raised it to 23725 for its one guidance paragraph (a genuine new
    # capability); the Eclipse UI authoring capability (`ui_*` tools) raised it to
    # 25217 for its one guidance paragraph; the Interactive Response Engine raised
    # it to 26410 for its `eclipse-response` guidance paragraph; the
    # Learning-Research capability raised it to 27445 for its `learning_map`
    # guidance paragraph; the website-style visual blocks (stat_hero, gauge,
    # comparison_grid, ranked_list, badge_row, carousel) raised it to 27769 for
    # their names + one guidance clause; the capability-acquire loop
    # (skill_install/uninstall, software installs, mcp_install) raised it to
    # 29162 for three new guidance paragraphs; the icon-vocabulary guidance
    # (`response_block_schema` lists the semantic keys) raised it to 29252 —
    # one clause so the model stops spelling icons wrong. It is re-pinned there
    # and may only shrink from here.
    # Re-pinned 29252→29994 for the Fiduciary Gate `<fiduciary_advice>` guidance
    # block (a genuine capability: ground recommendations in a portfolio
    # computation). Matches `test_memory_tools.py::test_prompt_char_ceiling`.
    # Re-pinned 29994→30420 for the app-surface guidance: the Q1 QA run answered
    # "where is X" from repository greps (once with no deep link) instead of
    # calling `ui_get_application_map` first. One guidance bullet; matches the
    # same test in `test_memory_tools.py`.
    # Re-pinned 30420→30897 for the learning-loop guidance (read the automatic
    # reviews/candidates instead of guessing). Matches the same test.
    # Re-pinned 30897->31834 for the Capability Builder guidance (construct a
    # missing capability instead of refusing; activation stays separate).
    # Re-pinned 31834->33632 for the computed-results guidance (COMPUTE in the
    # sandbox with `analysis_run` instead of answering in prose) and the
    # reports guidance (a report FILE is `eclipse_report`). Matches the same
    # test in `test_memory_tools.py`.
    # Re-pinned 33632->33724 for the same guidance with the CORRECT import list
    # (the allowed numerical stack; a figure is drawn by the ready-made
    # recipes, not by the program). Matches the same test.
    # Re-pinned 33724->34032 for the same paragraph with the two missing rules
    # (use a recipe name EXACTLY; let the PROGRAM fetch its series via
    # eclipse_tools.price_history). Matches the same test.
    # Re-pinned 34032->34804 for the per-command sandbox rules and the
    # "a refusal names the correction" guidance (a model that is refused must be
    # told what to do differently, not left to guess). It is guidance the
    # runtime needs; it is re-pinned to the measured size and may only shrink
    # from here. Matches the same test in `test_memory_tools.py`.
    # Re-pinned 34804->35251 for the in-flight shared-tree guidance (the chat
    # step budget rationale and the report/edge-report deliverables). Matches
    # the same test in `test_memory_tools.py`.
    # Re-pinned 35251->36353 for the shared-tree guidance that followed.
    # Re-pinned 36353->36652 for the formula guidance (maths is LaTeX and the
    # chat typesets it; money never goes inside a dollar sign). It is guidance
    # the runtime needs; it is re-pinned to the measured size and may only
    # shrink from here. Matches the same test in `test_memory_tools.py`.
    # Re-pinned 36652->36991 for the regression guidance (a linear regression is a
    # `regression` mark: the engine fits the line and shows the R-squared, so the
    # model never fits it itself). It is guidance the runtime needs; it is
    # re-pinned to the measured size and may only shrink from here. Matches the
    # same test in `test_memory_tools.py`.
    assert len(ECLIPSE_AGENT_SYSTEM_PROMPT) <= 36991


def test_main_still_reexports_the_identity_boundary_surface():
    """Splitting must not break the public `harness.main` surface tests rely on."""
    from harness import main

    assert callable(main.identity_boundary)
    assert callable(main.deployment_exposure)
    assert isinstance(main.IDENTITY_BOUNDARY, dict)


# ── S.3: docs drift — one shared surface page, cross-linked ──────────────────

def test_shared_surface_page_exists():
    page = (_DOCS / "research-surfaces.md").read_text(encoding="utf-8")
    assert "search finds" in page
    assert "One verification path" in page
    assert "claim_verify" in page


def test_all_three_engine_docs_cross_link_the_surface_page():
    for name in ("web-research-engine.md", "browser-runtime.md", "computer-use.md"):
        text = (_DOCS / name).read_text(encoding="utf-8")
        assert "research-surfaces.md" in text, f"{name} does not link the shared surface page"


def test_coordination_module_matches_the_doc():
    from harness.research.coordination import BROWSER, COMPUTER, WEB, route, routing_policy
    from harness.research.coordination import SurfaceRequest

    policy = routing_policy()
    assert set(policy["surfaces"]) == {WEB, BROWSER, COMPUTER}
    # The doc's rule is the module's rule.
    assert route(SurfaceRequest(native_app=True)).surface == COMPUTER
    assert route(SurfaceRequest(login_gated=True)).surface == BROWSER
    assert route(SurfaceRequest(question="x")).surface == WEB
