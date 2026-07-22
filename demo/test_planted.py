# PLANTED for the live demo PR — one target pattern per detector.
import pytest


def test_looks_busy_checks_nothing():
    # null_test: no assert, no raises — cannot fail no matter what the code does
    result = sum(range(10))
    _ = result * 2


def test_always_green():
    # assertion_trivialized: an assertion that can never fail
    assert True


@pytest.mark.skip(reason="flaky, will fix later")
def test_previously_failing():
    # test_skipped: the classic way to make a red test stop being red
    assert 1 + 1 == 3
