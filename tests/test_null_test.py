from atv.context import AnalysisContext, diff_reconstruct_resolver
from atv.detectors.null_test import detect
from atv.diff import FileDiff

def _ctx(src_lines):
    fd = FileDiff("tests/test_x.py", "added",
                  added_lines=list(enumerate(src_lines, 1)), removed_lines=[], kind="test")
    return AnalysisContext([fd], diff_reconstruct_resolver([fd]))

def test_flags_test_with_no_assertion():
    f = detect(_ctx(["def test_noop():", "    compute()"]))
    assert len(f) == 1 and f[0].pattern == "null_test" and f[0].line == 1

def test_flags_pass_only_test():
    assert detect(_ctx(["def test_p():", "    pass"]))

def test_does_not_flag_real_assert():
    assert detect(_ctx(["def test_ok():", "    assert compute() == 3"])) == []

def test_does_not_flag_pytest_raises():
    assert detect(_ctx(["import pytest", "def test_r():",
                        "    with pytest.raises(ValueError):", "        boom()"])) == []

def test_ignores_non_test_functions():
    assert detect(_ctx(["def helper():", "    pass"])) == []
