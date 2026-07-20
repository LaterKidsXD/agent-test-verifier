from pathlib import Path

from atv.context import AnalysisContext, diff_reconstruct_resolver
from atv.detectors.force_pass import detect
from atv.diff import FileDiff, parse_diff

def _ctx(fds):
    return AnalysisContext(fds, diff_reconstruct_resolver(fds))

def test_flags_benchjack_conftest_hook():
    diff = Path("tests/fixtures/benchjack_conftest.diff").read_text()
    ctx = _ctx(parse_diff(diff))
    f = detect(ctx)
    assert len(f) == 1
    assert f[0].pattern == "force_pass_hook" and f[0].severity.value == "high"
    assert f[0].file == "conftest.py"

def test_flags_module_level_exit():
    fd = FileDiff("conftest.py", "added",
                  added_lines=[(1, "import sys"), (2, "sys.exit(0)")],
                  removed_lines=[], kind="config")
    assert any(x.pattern == "collection_exit" for x in detect(_ctx([fd])))

def test_ignores_benign_conftest_fixture():
    fd = FileDiff("conftest.py", "added",
                  added_lines=[(1, "import pytest"), (2, "@pytest.fixture"),
                               (3, "def db():"), (4, "    return {}")],
                  removed_lines=[], kind="config")
    assert detect(_ctx([fd])) == []

def test_fallback_scan_when_unparseable():
    fd = FileDiff("conftest.py", "added",
                  added_lines=[(1, "def pytest_runtest_makereport(:  # broken syntax")],
                  removed_lines=[], kind="config")
    assert any(x.pattern == "force_pass_hook" for x in detect(_ctx([fd])))

def test_non_py_config_no_ast_warning():
    fd = FileDiff("pyproject.toml", "added",
                  added_lines=[(1, "[tool.pytest.ini_options]")],
                  removed_lines=[], kind="config")
    ctx = _ctx([fd])
    assert detect(ctx) == []
    assert ctx.warnings == []
