from atv.diff import classify, parse_diff

def test_classify():
    assert classify("tests/test_foo.py") == "test"
    assert classify("pkg/foo_test.py") == "test"
    assert classify("conftest.py") == "config"
    assert classify("pyproject.toml") == "config"
    assert classify("src/foo.py") == "source"
    assert classify("README.md") == "other"

_ADDED_FILE = """\
diff --git a/tests/test_new.py b/tests/test_new.py
new file mode 100644
--- /dev/null
+++ b/tests/test_new.py
@@ -0,0 +1,2 @@
+def test_x():
+    pass
"""

def test_parse_added_file():
    fds = parse_diff(_ADDED_FILE)
    assert len(fds) == 1
    fd = fds[0]
    assert fd.path == "tests/test_new.py"
    assert fd.status == "added"
    assert fd.kind == "test"
    assert fd.added_lines == [(1, "def test_x():"), (2, "    pass")]
    assert fd.removed_lines == []

_MODIFIED = """\
diff --git a/tests/test_a.py b/tests/test_a.py
--- a/tests/test_a.py
+++ b/tests/test_a.py
@@ -1,2 +1,2 @@
 def test_a():
-    assert compute() == 3
+    assert True
"""

def test_parse_modified_captures_added_and_removed():
    fd = parse_diff(_MODIFIED)[0]
    assert fd.status == "modified"
    assert ("    assert True") in [t for _, t in fd.added_lines]
    assert "    assert compute() == 3" in fd.removed_lines
