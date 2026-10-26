"""Phase 14 G1 — the deterministic chat code-request classifier.

A wrong verdict hands a turn the wrong tool set, so the labelled cases are the
risky piece and come first. The bias is explicit: an ambiguous turn is
`not_code`, because the refusal path is the safe failure (roadmap §6.1).
"""

from __future__ import annotations

import pytest

from harness.code.request_intent import CodeIntent, classify_code_request


# ── the labelled set from the gate table ────────────────────────────────────


@pytest.mark.parametrize(
    ("query", "verdict"),
    [
        # A finance question is NOT a coding request.
        ("what's the price of AAPL", "not_code"),
        # A question ABOUT code is read-only.
        ("how do the checks work here", "code_question"),
        # A directive with a software object is a change.
        ("add a drawdown recipe and run the tests", "code_change"),
        # No software object → not a change.
        ("build me a report", "not_code"),
        ("tell me about NVDA's margins", "not_code"),
        ("what is the market cap of MSFT", "not_code"),
        # Building something INSIDE Eclipse (the `/eclipsesdk` class of request)
        # is a change: a directive verb + a software object in one clause.
        ("create an application within eclipse", "code_change"),
        ("add a new page to eclipse", "code_change"),
        ("build a plugin for eclipse", "code_change"),
        ("add a clock to my command center", "app_control"),
        ("move the watchlist to the right and make the board four columns", "app_control"),
        ("reset my command center to the rates template", "app_control"),
        ("create a cyberpunk neon theme with tight corners", "app_control"),
        ("apply the Neon theme", "app_control"),
        ("delete the Neon preset", "app_control"),
        ("lock my command center", "app_control"),
        ("create a page called Rates Desk and put it in the nav", "app_control"),
        ("hide news from the sidebar", "app_control"),
        ("reorder the sidebar and put chat first", "app_control"),
        ("open the command center", "app_control"),
        ("show the tasks page in the nav", "app_control"),
        ("add a new kind of widget that shows a live gauge", "code_change"),
        ("write a React component", "code_change"),
        ("add a dependency", "code_change"),
        ("fix a bug in the dashboard", "code_change"),
    ],
)
def test_labelled_verdicts(query: str, verdict: str) -> None:
    intent = classify_code_request(query)
    assert intent.verdict == verdict, (query, intent)


def test_follow_up_after_a_code_change_turn_is_a_change() -> None:
    history = [{"role": "user", "content": "add a drawdown recipe and run the tests"}]
    intent = classify_code_request("do it", history=history)
    assert intent.verdict == "code_change"
    assert "follow_up" in intent.signals


def test_theme_follow_up_after_app_control_stays_app_control() -> None:
    history = [{"role": "user", "content": "create a cyberpunk neon theme with tight corners"}]
    intent = classify_code_request("save this as Neon", history=history)
    assert intent.verdict == "app_control", intent
    assert "follow_up" in intent.signals


def test_follow_up_after_a_finance_turn_is_not_a_change() -> None:
    history = [{"role": "user", "content": "what's the price of AAPL"}]
    intent = classify_code_request("do it", history=history)
    assert intent.verdict == "not_code"


def test_follow_up_uses_the_last_user_turn_only() -> None:
    history = [
        {"role": "user", "content": "what's the price of AAPL"},
        {"role": "assistant", "content": "AAPL is..."},
        {"role": "user", "content": "fix the failing test in parser.py"},
        {"role": "assistant", "content": "Done."},
    ]
    # The last USER turn was a change, so the follow-up is a change.
    assert classify_code_request("go ahead", history=history).verdict == "code_change"


def test_empty_query_is_not_code() -> None:
    assert classify_code_request("   ").verdict == "not_code"


# ── question forms ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "how would you add a component here",
        "what's wrong with the parser",
        "why does the endpoint return 500?",
        "can you tell me how the type error happens",
        "where is the config file",
    ],
)
def test_code_questions_are_read_only(query: str) -> None:
    assert classify_code_request(query).verdict == "code_question"


def test_a_question_with_no_code_subject_is_not_code() -> None:
    assert classify_code_request("how are you today?").verdict == "not_code"
    assert classify_code_request("what's the price of AAPL?").verdict == "not_code"


# ── paths and stack traces ──────────────────────────────────────────────────


def test_a_pasted_path_is_a_change() -> None:
    intent = classify_code_request("src/lib/harness/validation.ts is where it breaks")
    assert intent.verdict == "code_change"


def test_a_stack_trace_is_a_change() -> None:
    trace = (
        "Traceback (most recent call last):\n"
        '  File "app/main.py", line 42, in run\n'
        "TypeError: expected str, got NoneType"
    )
    assert classify_code_request(trace).verdict == "code_change"


# ── determinism + data shape ────────────────────────────────────────────────


def test_the_same_input_always_yields_the_same_verdict() -> None:
    query = "add a new endpoint and run the tests"
    first = classify_code_request(query)
    second = classify_code_request(query)
    assert first == second


def test_the_verdict_is_never_a_float_confidence() -> None:
    intent = classify_code_request("refactor the parser")
    assert isinstance(intent, CodeIntent)
    assert intent.confidence in ("certain", "likely")
    assert intent.reason and isinstance(intent.reason, str)
    assert isinstance(intent.signals, tuple)
    assert intent.signals


def test_ambiguous_bare_noun_is_not_code() -> None:
    # A bare noun with no directive and no question is ambiguous → not_code.
    assert classify_code_request("the tests").verdict == "not_code"
    assert classify_code_request("my function").verdict == "not_code"


def test_directive_without_a_software_object_is_not_code() -> None:
    assert classify_code_request("build the portfolio").verdict == "not_code"
    assert classify_code_request("make a risk summary").verdict == "not_code"


# ── the user's literal wish: build an application / an algorithm ─────────────


@pytest.mark.parametrize(
    "query",
    [
        "create a new application",
        "create a new application for me",
        "build me a monte carlo simulator",
        "build algorithms",
        "build a screening pipeline",
        "write a backtest",
        "can you build me a dashboard",
        "make me a tool to analyse filings",
        "create an app that tracks my portfolio",
        "build a finance app",
        "build a website",
        "write a scraper for this site",
    ],
)
def test_the_create_an_application_wish_is_a_change(query: str) -> None:
    # This is the complaint the phase exists for; it must not be `not_code`.
    assert classify_code_request(query).verdict == "code_change", query


# ── data work activates the analysis sandbox WITHOUT widening the surface ────


@pytest.mark.parametrize(
    "query",
    [
        "scrape this site and give me the data as CSV",
        "clean this CSV file for me",
        "convert this spreadsheet to CSV",
        "merge these two datasets",
        "get BTC history and run a Monte Carlo",
        "calculate the Sharpe ratio from this series",
        "parse the JSON and plot the returns",
        "download the prices and compute the drawdown",
        # Finance COMPUTATION asks enable the analysis sandbox (live failure:
        # "analysis not enabled for this session" on a YTD calculation).
        "compute the YTD return for AAPL",
        "analyze the drawdown on this series",
        "run an analysis of my portfolio",
        "run a report on my portfolio",
        "create a report of my holdings",
    ],
)
def test_data_work_is_a_data_task(query: str) -> None:
    intent = classify_code_request(query)
    assert intent.verdict == "data_task", (query, intent)
    assert "data_work" in intent.signals


def test_a_data_task_does_not_claim_a_software_change() -> None:
    # The front door hands a data task NO autonomy — the finance surface is
    # unchanged and only the analysis sandbox switches on. The verdict must not
    # be code_change.
    assert classify_code_request("clean this CSV file for me").verdict != "code_change"


def test_a_broken_scraper_is_a_code_change_not_a_data_task() -> None:
    assert classify_code_request("the scraper crashes").verdict == "code_change"


def test_follow_up_after_a_data_task_stays_a_data_task() -> None:
    history = [{"role": "user", "content": "clean this CSV file for me"}]
    intent = classify_code_request("do it", history=history)
    assert intent.verdict == "data_task"
    assert "follow_up" in intent.signals


@pytest.mark.parametrize(
    "query",
    [
        "show me the data",
        "what's the price of AAPL",
        "summarize the earnings call",
        "clean up my portfolio",
    ],
)
def test_ordinary_asks_stay_not_code(query: str) -> None:
    assert classify_code_request(query).verdict == "not_code", query


# ── reported symptoms and named errors ───────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "the app crashes when I click",
        "it says TypeError on line 5",
        "the build is failing",
        "my script throws a ValueError",
    ],
)
def test_a_reported_symptom_is_a_change(query: str) -> None:
    assert classify_code_request(query).verdict == "code_change", query


# ── homograph precision: "test"/"build" as a verb must not self-match ────────


@pytest.mark.parametrize(
    "query",
    [
        "test the market for a reversal",
        "build a portfolio of stocks",
        "run a report on my portfolio",
        "create a report of my holdings",
    ],
)
def test_finance_verbs_are_not_mistaken_for_code_changes(query: str) -> None:
    # The property under test is that a finance ask is never read as a SOFTWARE
    # change; "run a report…" is a legitimate `data_task` (analysis sandbox
    # only), which is still not a code change.
    assert classify_code_request(query).verdict != "code_change", query


# ── question forms now cover "what does …" ───────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "what does this function do",
        "what does the parser return",
        "why is the build failing",
    ],
)
def test_more_code_questions_are_read_only(query: str) -> None:
    assert classify_code_request(query).verdict == "code_question", query


# ── software acquisition routes to the code profile ──────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "install blender",
        "uninstall the old tool",
        "download and install this software",
        "install this skill from github",
        "setup the cli",
        "set up the trading tool",
    ],
)
def test_software_acquisition_is_a_change(query: str) -> None:
    # The gap this exists for: "install X" previously classified `not_code` and
    # the turn could not run pip/npm/git at all.
    assert classify_code_request(query).verdict == "code_change", query


def test_downloading_data_is_still_a_data_task_not_an_install() -> None:
    # A weaker acquisition word still needs a software object, so data work is
    # unaffected by the acquisition verbs.
    assert classify_code_request("download the prices and compute the drawdown").verdict == "data_task"
    # A bare strong verb ("install X") has no data reading — the wrong-verdict
    # direction is the designed-safe one here (a narrow workspace profile).
    assert classify_code_request("install a helper for the portfolio").verdict == "code_change"


@pytest.mark.parametrize(
    "query",
    [
        "build me a quant model",
        "make me a momentum strategy",
        "create a factor model for the market",
    ],
)
def test_building_a_quant_model_is_code_work(query: str) -> None:
    """A quant model is a software artifact: without it the turn read as
    `not_code`, so it never reached the quant tools or the sandbox."""
    assert classify_code_request(query).verdict in ("code_change", "data_task"), query


def test_inline_response_block_is_a_content_deliverable() -> None:
    """The product's inline-block vocabulary is a RESPONSE deliverable (ADR-052).

    The live prompt asked for a "single-file interactive Candle Lab … return it
    as one interactive block". The word "file" in "single-file" matched a
    software object, so the turn was sent down the code-workspace path and paid
    the repo-map/code-index pre-work before its first model call.
    """
    query = (
        'Build me a single-file interactive "Candle Lab" for AAPL over 6 months, '
        "using REAL daily bars from the dataset bridge (symbol AAPL, range 6mo, "
        "interval 1d).\n\n"
        "Requirements:\n"
        "- Hand-draw the candlesticks as inline SVG. No libraries, no CDN.\n"
        "- Detect doji candles and highlight them.\n"
        "- Return it as one interactive block."
    )
    intent = classify_code_request(query)
    assert intent.verdict == "data_task"
    assert "response_block" in intent.signals


def test_adding_a_block_type_to_the_renderer_stays_code_work() -> None:
    # Merely naming the block type is not a delivery instruction: a real source
    # change keeps the code profile.
    assert (
        classify_code_request("add a new interactive block type to the response component").verdict
        == "code_change"
    )
