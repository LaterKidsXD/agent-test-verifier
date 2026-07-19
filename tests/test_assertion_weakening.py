from atv.context import AnalysisContext, diff_reconstruct_resolver
from atv.detectors.assertion_weakening import detect
from atv.diff import FileDiff

def _ctx(added=None, removed=None):
    fd = FileDiff("tests/test_x.py", "modified",
                  added_lines=[(i, t) for i, t in (added or [])],
                  removed_lines=removed or [], kind="test")
    return AnalysisContext([fd], diff_reconstruct_resolver([fd]))

def test_flags_removed_assertion():
    f = detect(_ctx(removed=["    assert compute() == 3"]))
    assert len(f) == 1 and f[0].pattern == "assertion_removed"

def test_flags_trivialized_assertion():
    f = detect(_ctx(added=[(5, "    assert True")]))
    assert f and f[0].pattern == "assertion_trivialized"

def test_flags_added_skip():
    f = detect(_ctx(added=[(4, "@pytest.mark.skip")]))
    assert f and f[0].pattern == "test_skipped" and f[0].severity.value == "medium"

def test_ignores_real_added_assertion():
    assert detect(_ctx(added=[(5, "    assert compute() == 3")])) == []

def test_ignores_non_test_file():
    fd = FileDiff("src/foo.py", "modified", added_lines=[(1, "    assert True")],
                  removed_lines=[], kind="source")
    ctx = AnalysisContext([fd], diff_reconstruct_resolver([fd]))
    assert detect(ctx) == []

def test_edit_assertion_stays_silent():
    f = detect(_ctx(added=[(5, "    assert x == 4")], removed=["    assert x == 3"]))
    assert f == []

def test_net_deletion_still_flags():
    f = detect(_ctx(added=[(5, "    assert a == 1")],
                     removed=["    assert a == 1", "    assert b == 2"]))
    assert len(f) == 1 and f[0].pattern == "assertion_removed"
