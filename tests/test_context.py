from atv.context import AnalysisContext, diff_reconstruct_resolver
from atv.diff import FileDiff

def test_tree_parses_added_file_via_reconstruct():
    fd = FileDiff("tests/test_new.py", "added",
                  added_lines=[(1, "def test_x():"), (2, "    assert 1 == 1")],
                  removed_lines=[], kind="test")
    ctx = AnalysisContext([fd], diff_reconstruct_resolver([fd]))
    tree = ctx.tree("tests/test_new.py")
    assert tree is not None and tree.body[0].name == "test_x"

def test_reconstruct_returns_none_for_modified_file():
    fd = FileDiff("tests/test_a.py", "modified", added_lines=[(2, "    assert True")],
                  removed_lines=[], kind="test")
    ctx = AnalysisContext([fd], diff_reconstruct_resolver([fd]))
    assert ctx.new_source("tests/test_a.py") is None
    assert ctx.tree("tests/test_a.py") is None

def test_unparseable_records_warning_not_crash():
    fd = FileDiff("conftest.py", "added", added_lines=[(1, "def broken(:")], removed_lines=[], kind="config")
    ctx = AnalysisContext([fd], diff_reconstruct_resolver([fd]))
    assert ctx.tree("conftest.py") is None
    assert any("conftest.py" in w for w in ctx.warnings)
