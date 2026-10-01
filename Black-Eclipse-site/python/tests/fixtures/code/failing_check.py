"""A failing pytest fixture: a failing test (exit non-zero)."""


def test_fails_as_designed():
    assert 1 + 1 == 3, "check failed as designed"
