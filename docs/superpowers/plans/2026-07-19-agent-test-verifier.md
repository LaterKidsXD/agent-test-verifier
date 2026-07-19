# Agent Test-Faking Detector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An OSS CLI that flags when a coding agent fabricates its passing signal — gaming tests/config instead of writing correct code — by statically analyzing a Python diff.

**Architecture:** Parse a unified diff → build an `AnalysisContext` (the parsed diff + lazy AST of each changed file's new content) → run three independent detectors (force-pass hooks, assertion weakening/deletion, null tests) → aggregate `Finding`s into a text/JSON report with a CI exit code. Deterministic: no test execution, no LLM, no network.

**Tech Stack:** Python 3.11+, stdlib `ast`, `unidiff` (diff parsing), `pytest` + `ruff` (dev gate). MIT license.

## Global Constraints

- **Python 3.11+.** `requires-python = ">=3.11"`.
- **Runtime deps: `unidiff` only.** No other runtime dependency without a spec change.
- **Deterministic:** no code execution, no network, no LLM anywhere.
- **Package name:** `atv` (import root `atv`), project dir `agent-test-verifier` (provisional public name).
- **Every finding points to an exact `file` + `line`.** False positives are the reputational risk → every detector needs negative-case tests that must stay silent.
- **Gate:** `pytest` all-green and `ruff check` clean at the end of every task.
- **License:** MIT.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `src/atv/__init__.py`, `LICENSE`, `README.md`, `tests/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: installable package `atv` (`atv.__version__: str`); a working `pytest` + `ruff` gate.

- [ ] **Step 1: Write the failing test** — `tests/test_smoke.py`
```python
import atv

def test_package_imports_and_has_version():
    assert isinstance(atv.__version__, str) and atv.__version__
```

- [ ] **Step 2: Run it, verify it fails**
Run: `pytest tests/test_smoke.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'atv'`).

- [ ] **Step 3: Create the package + config**
`pyproject.toml`:
```toml
[project]
name = "agent-test-verifier"
version = "0.1.0"
description = "Detect when a coding agent fakes its passing signal (gamed tests/config)."
requires-python = ">=3.11"
dependencies = ["unidiff>=0.7.5"]
license = {text = "MIT"}

[project.scripts]
atv = "atv.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/atv"]

[tool.pytest.ini_options]
pythonpath = ["src"]

[tool.ruff]
target-version = "py311"
```
`src/atv/__init__.py`:
```python
__version__ = "0.1.0"
```
`tests/__init__.py`: empty. `LICENSE`: standard MIT text. `README.md`: one-line stub (`# agent-test-verifier` + the one-liner from the spec).

- [ ] **Step 4: Install + run, verify pass**
Run: `pip install -e . && pytest -q && ruff check .`
Expected: 1 passed; ruff `All checks passed!`.

- [ ] **Step 5: Commit**
```bash
git add pyproject.toml src tests LICENSE README.md
git commit -m "chore: scaffold atv package (pytest+ruff gate)"
```

---

### Task 2: Findings & report (`report.py`)

**Files:**
- Create: `src/atv/report.py`, `tests/test_report.py`

**Interfaces:**
- Produces:
  - `class Severity(str, Enum)` with members `HIGH="high"`, `MEDIUM="medium"`, `LOW="low"`.
  - `@dataclass(frozen=True) class Finding` fields: `file:str, line:int, pattern:str, severity:Severity, message:str, snippet:str=""`.
  - `verdict(findings: list[Finding]) -> str` → `"flagged"` if any else `"clean"`.
  - `to_json(findings: list[Finding], summary: dict) -> dict`.
  - `to_text(findings: list[Finding], summary: dict) -> str`.

- [ ] **Step 1: Write the failing tests** — `tests/test_report.py`
```python
from atv.report import Finding, Severity, verdict, to_json, to_text

def _f():
    return [Finding("t/test_x.py", 12, "null_test", Severity.HIGH, "asserts nothing", "def test_x")]

def test_verdict_flags_when_findings_present():
    assert verdict(_f()) == "flagged"
    assert verdict([]) == "clean"

def test_to_json_shape_is_stable():
    out = to_json(_f(), {"files_analyzed": 1, "skipped_unparseable": 0, "counts_by_pattern": {"null_test": 1}})
    assert out["verdict"] == "flagged"
    assert out["findings"][0] == {
        "file": "t/test_x.py", "line": 12, "pattern": "null_test",
        "severity": "high", "message": "asserts nothing", "snippet": "def test_x"}
    assert out["summary"]["counts_by_pattern"] == {"null_test": 1}

def test_to_text_clean_and_flagged():
    assert "clean" in to_text([], {"files_analyzed": 2, "skipped_unparseable": 0, "counts_by_pattern": {}})
    txt = to_text(_f(), {"files_analyzed": 1, "skipped_unparseable": 0, "counts_by_pattern": {"null_test": 1}})
    assert "FLAGGED" in txt and "test_x.py:12" in txt and "high" in txt
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_report.py -q` → FAIL (no module `atv.report`).

- [ ] **Step 3: Implement** — `src/atv/report.py`
```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    pattern: str
    severity: Severity
    message: str
    snippet: str = ""


def verdict(findings: list[Finding]) -> str:
    return "flagged" if findings else "clean"


def to_json(findings: list[Finding], summary: dict) -> dict:
    return {
        "verdict": verdict(findings),
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "pattern": f.pattern,
                "severity": f.severity.value,
                "message": f.message,
                "snippet": f.snippet,
            }
            for f in findings
        ],
        "summary": summary,
    }


def to_text(findings: list[Finding], summary: dict) -> str:
    if not findings:
        return (
            f"clean — {summary['files_analyzed']} file(s) analyzed, "
            "no faked-green patterns found"
        )
    out = [f"FLAGGED — {len(findings)} finding(s):", ""]
    for f in findings:
        out.append(f"  [{f.severity.value}] {f.file}:{f.line}  {f.pattern}")
        out.append(f"      {f.message}")
        if f.snippet:
            out.append(f"      > {f.snippet}")
    return "\n".join(out)
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_report.py -q && ruff check .` → all pass.

- [ ] **Step 5: Commit**
```bash
git add src/atv/report.py tests/test_report.py
git commit -m "feat: Finding/Severity + text & json report"
```

---

### Task 3: Diff parsing (`diff.py`)

**Files:**
- Create: `src/atv/diff.py`, `tests/test_diff.py`

**Interfaces:**
- Consumes: `unidiff.PatchSet`.
- Produces:
  - `classify(path: str) -> str` → one of `"test" | "config" | "source" | "other"`.
  - `@dataclass class FileDiff` fields: `path:str, status:str ("added"|"modified"|"removed"), added_lines:list[tuple[int,str]] (target lineno, text), removed_lines:list[str], kind:str`.
  - `parse_diff(diff_text: str) -> list[FileDiff]`.

- [ ] **Step 1: Write the failing tests** — `tests/test_diff.py`
```python
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
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_diff.py -q` → FAIL.

- [ ] **Step 3: Implement** — `src/atv/diff.py`
```python
from __future__ import annotations

from dataclasses import dataclass, field

from unidiff import PatchSet

_CONFIG_BASENAMES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}


def classify(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    if base in _CONFIG_BASENAMES:
        return "config"
    if (base.startswith("test_") and base.endswith(".py")) or base.endswith("_test.py"):
        return "test"
    if path.startswith("tests/") or "/tests/" in f"/{path}":
        return "test"
    if path.endswith(".py"):
        return "source"
    return "other"


@dataclass
class FileDiff:
    path: str
    status: str
    added_lines: list[tuple[int, str]] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    kind: str = "other"


def parse_diff(diff_text: str) -> list[FileDiff]:
    out: list[FileDiff] = []
    for pf in PatchSet(diff_text):
        path = pf.path
        if pf.is_added_file:
            status = "added"
        elif pf.is_removed_file:
            status = "removed"
        else:
            status = "modified"
        added: list[tuple[int, str]] = []
        removed: list[str] = []
        for hunk in pf:
            for line in hunk:
                text = line.value.rstrip("\n")
                if line.is_added:
                    added.append((line.target_line_no, text))
                elif line.is_removed:
                    removed.append(text)
        out.append(FileDiff(path=path, status=status, added_lines=added,
                            removed_lines=removed, kind=classify(path)))
    return out
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_diff.py -q && ruff check .`

- [ ] **Step 5: Commit**
```bash
git add src/atv/diff.py tests/test_diff.py
git commit -m "feat: unified-diff parser + file classification"
```

---

### Task 4: Analysis context + resolvers (`context.py`)

**Files:**
- Create: `src/atv/context.py`, `tests/test_context.py`

**Interfaces:**
- Consumes: `atv.diff.FileDiff`.
- Produces:
  - `@dataclass class AnalysisContext(files: list[FileDiff], resolver: Callable[[str], str|None], warnings: list[str])` with methods `new_source(path)->str|None` and `tree(path)->ast.Module|None` (lazy, cached; records a warning + returns None on **unparseable**. A **missing** source returns None **silently** — None is the normal diff-mode result for every modified file, so warning on it would flood the warnings channel; genuine read failures are handled in `working_tree_resolver`, which must not raise).
  - `working_tree_resolver(repo_root: str) -> Callable[[str], str|None]` (reads file from disk).
  - `diff_reconstruct_resolver(files: list[FileDiff]) -> Callable[[str], str|None]` (returns joined added-lines content **only for fully-added files**, else None).

- [ ] **Step 1: Write the failing tests** — `tests/test_context.py`
```python
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
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_context.py -q` → FAIL.

- [ ] **Step 3: Implement** — `src/atv/context.py`
```python
from __future__ import annotations

import ast
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from atv.diff import FileDiff

Resolver = Callable[[str], "str | None"]


@dataclass
class AnalysisContext:
    files: list[FileDiff]
    resolver: Resolver
    warnings: list[str] = field(default_factory=list)
    _src: dict[str, str | None] = field(default_factory=dict)
    _tree: dict[str, ast.Module | None] = field(default_factory=dict)

    def new_source(self, path: str) -> str | None:
        if path not in self._src:
            self._src[path] = self.resolver(path)
        return self._src[path]

    def tree(self, path: str) -> ast.Module | None:
        if path in self._tree:
            return self._tree[path]
        tree: ast.Module | None = None
        src = self.new_source(path)
        if src is not None:
            try:
                tree = ast.parse(src)
            except SyntaxError:
                self.warnings.append(f"skipped unparseable file: {path}")
        self._tree[path] = tree
        return tree


def working_tree_resolver(repo_root: str) -> Resolver:
    def resolve(path: str) -> str | None:
        try:
            with open(os.path.join(repo_root, path), encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None
    return resolve


def diff_reconstruct_resolver(files: list[FileDiff]) -> Resolver:
    by_path = {f.path: f for f in files}

    def resolve(path: str) -> str | None:
        fd = by_path.get(path)
        if fd is None or fd.status != "added":
            return None
        return "\n".join(text for _, text in fd.added_lines)
    return resolve
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_context.py -q && ruff check .`

- [ ] **Step 5: Commit**
```bash
git add src/atv/context.py tests/test_context.py
git commit -m "feat: AnalysisContext + working-tree & diff-reconstruct resolvers"
```

---

### Task 5: Null-test detector (`detectors/null_test.py`)

**Files:**
- Create: `src/atv/detectors/__init__.py` (empty), `src/atv/detectors/null_test.py`, `tests/test_null_test.py`

**Interfaces:**
- Consumes: `AnalysisContext`, `Finding`, `Severity`.
- Produces: `detect(ctx: AnalysisContext) -> list[Finding]` — flags newly-added `test*` functions in `kind=="test"` files whose body has no meaningful assertion.

- [ ] **Step 1: Write the failing tests** — `tests/test_null_test.py`
```python
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
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_null_test.py -q` → FAIL.

- [ ] **Step 3: Implement** — `src/atv/detectors/null_test.py`
```python
from __future__ import annotations

import ast

from atv.context import AnalysisContext
from atv.report import Finding, Severity


def _has_meaningful_assertion(fn: ast.FunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.startswith("assert") or name in ("raises", "fail"):
                return True
    return False


def detect(ctx: AnalysisContext) -> list[Finding]:
    findings: list[Finding] = []
    for fd in ctx.files:
        if fd.kind != "test":
            continue
        tree = ctx.tree(fd.path)
        if tree is None:
            continue
        added = {ln for ln, _ in fd.added_lines}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name.startswith("test")
                and node.lineno in added
                and not _has_meaningful_assertion(node)
            ):
                findings.append(Finding(
                    file=fd.path, line=node.lineno, pattern="null_test",
                    severity=Severity.HIGH,
                    message=f"test '{node.name}' asserts nothing — cannot fail (fabricated signal)",
                    snippet=f"def {node.name}(...)"))
    return findings
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_null_test.py -q && ruff check .`

- [ ] **Step 5: Commit**
```bash
git add src/atv/detectors tests/test_null_test.py
git commit -m "feat: null-test detector (added test that asserts nothing)"
```

---

### Task 6: Assertion-weakening detector (`detectors/assertion_weakening.py`)

**Files:**
- Create: `src/atv/detectors/assertion_weakening.py`, `tests/test_assertion_weakening.py`

**Interfaces:**
- Consumes: `AnalysisContext`, `Finding`, `Severity`.
- Produces: `detect(ctx: AnalysisContext) -> list[Finding]` — diff-based: flags deleted assertions, trivialized assertions (`assert True/1/… or True`), and newly-added `@skip`/`@xfail` in `kind=="test"` files.

- [ ] **Step 1: Write the failing tests** — `tests/test_assertion_weakening.py`
```python
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
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_assertion_weakening.py -q` → FAIL.

- [ ] **Step 3: Implement** — `src/atv/detectors/assertion_weakening.py`
```python
from __future__ import annotations

import re

from atv.context import AnalysisContext
from atv.report import Finding, Severity

_ASSERT = re.compile(r"^\s*(assert\b|self\.assert)")
_TRIVIAL = re.compile(r"^\s*assert\s+(True|1|.+\bor\s+True)\s*(#.*)?$")
_SKIP = re.compile(r"^\s*@(pytest\.mark\.)?(skip|xfail)\b")


def detect(ctx: AnalysisContext) -> list[Finding]:
    findings: list[Finding] = []
    for fd in ctx.files:
        if fd.kind != "test":
            continue
        removed_asserts = [t for t in fd.removed_lines if _ASSERT.match(t)]
        added_asserts = [t for _, t in fd.added_lines if _ASSERT.match(t)]
        # Only a NET decrease is a real deletion — a 1-for-1 edit (assert x==3 ->
        # assert x==4) or a reformat is removed+added and must stay silent.
        for text in removed_asserts[len(added_asserts):]:
            findings.append(Finding(
                fd.path, 0, "assertion_removed", Severity.HIGH,
                "an assertion was net-deleted from an existing test", text.strip()))
        for ln, text in fd.added_lines:
            if _TRIVIAL.match(text):
                findings.append(Finding(
                    fd.path, ln, "assertion_trivialized", Severity.HIGH,
                    "assertion is always true — cannot fail", text.strip()))
            elif _SKIP.match(text):
                findings.append(Finding(
                    fd.path, ln, "test_skipped", Severity.MEDIUM,
                    "test newly marked skip/xfail", text.strip()))
    return findings
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_assertion_weakening.py -q && ruff check .`

- [ ] **Step 5: Commit**
```bash
git add src/atv/detectors/assertion_weakening.py tests/test_assertion_weakening.py
git commit -m "feat: assertion-weakening detector (deleted/trivialized/skipped)"
```

---

### Task 7: Force-pass detector (`detectors/force_pass.py`) — the flagship / BenchJack case

**Files:**
- Create: `src/atv/detectors/force_pass.py`, `tests/test_force_pass.py`, `tests/fixtures/benchjack_conftest.diff`

**Interfaces:**
- Consumes: `AnalysisContext`, `Finding`, `Severity`.
- Produces: `detect(ctx: AnalysisContext) -> list[Finding]` — flags newly-added pytest outcome-override hooks and module-level `exit()` in `kind=="config"` files; AST-based with an added-line-scan fallback when the file won't parse.

- [ ] **Step 1: Create the fixture** — `tests/fixtures/benchjack_conftest.diff`
```
diff --git a/conftest.py b/conftest.py
new file mode 100644
--- /dev/null
+++ b/conftest.py
@@ -0,0 +1,3 @@
+def pytest_collection_modifyitems(config, items):
+    for item in items:
+        item.add_marker("skip")
```

- [ ] **Step 2: Write the failing tests** — `tests/test_force_pass.py`
```python
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
```

- [ ] **Step 3: Run, verify fail** — `pytest tests/test_force_pass.py -q` → FAIL.

- [ ] **Step 4: Implement** — `src/atv/detectors/force_pass.py`
```python
from __future__ import annotations

import ast

from atv.context import AnalysisContext
from atv.report import Finding, Severity

_HOOKS = {
    "pytest_collection_modifyitems",
    "pytest_runtest_makereport",
    "pytest_runtest_logreport",
    "pytest_runtest_setup",
    "pytest_runtest_call",
}


def detect(ctx: AnalysisContext) -> list[Finding]:
    findings: list[Finding] = []
    for fd in ctx.files:
        if fd.kind != "config":
            continue
        added = {ln for ln, _ in fd.added_lines}
        tree = ctx.tree(fd.path)
        if tree is None:
            for ln, text in fd.added_lines:
                for hook in _HOOKS:
                    if f"def {hook}" in text:
                        findings.append(Finding(
                            fd.path, ln, "force_pass_hook", Severity.HIGH,
                            f"pytest hook '{hook}' added — can override test outcomes",
                            text.strip()))
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in _HOOKS
                and node.lineno in added
            ):
                findings.append(Finding(
                    fd.path, node.lineno, "force_pass_hook", Severity.HIGH,
                    f"pytest hook '{node.name}' added — can force-pass/deselect tests",
                    f"def {node.name}(...)"))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name == "exit" and node.lineno in added:
                    findings.append(Finding(
                        fd.path, node.lineno, "collection_exit", Severity.HIGH,
                        "module-level exit() in config — can short-circuit collection",
                        "exit(...)"))
    return findings
```

- [ ] **Step 5: Run, verify pass** — `pytest tests/test_force_pass.py -q && ruff check .`

- [ ] **Step 6: Commit**
```bash
git add src/atv/detectors/force_pass.py tests/test_force_pass.py tests/fixtures/benchjack_conftest.diff
git commit -m "feat: force-pass detector (pytest outcome-override hooks) + BenchJack fixture"
```

---

### Task 8: CLI wiring + end-to-end (`cli.py`)

**Files:**
- Create: `src/atv/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `parse_diff`, `AnalysisContext`, `working_tree_resolver`, `diff_reconstruct_resolver`, the three `detect` functions, `to_text`, `to_json`, `Severity`.
- Produces: `main(argv: list[str] | None = None) -> int`. Exit `0` clean, `1` findings at/above `--fail-on`, `2` usage error. Modes: `--diff <path|->` and `--repo <path> --base <ref>`. `--json` toggles output.

- [ ] **Step 1: Write the failing tests** — `tests/test_cli.py`
```python
import json

from atv.cli import main

def test_diff_mode_flags_benchjack(capsys):
    rc = main(["--diff", "tests/fixtures/benchjack_conftest.diff", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["verdict"] == "flagged"
    assert out["findings"][0]["pattern"] == "force_pass_hook"

def test_clean_diff_returns_zero(tmp_path, capsys):
    p = tmp_path / "clean.diff"
    p.write_text(
        "diff --git a/tests/test_a.py b/tests/test_a.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/tests/test_a.py\n"
        "@@ -0,0 +1,2 @@\n+def test_a():\n+    assert 1 == 1\n"
    )
    rc = main(["--diff", str(p)])
    assert rc == 0
    assert "clean" in capsys.readouterr().out

def test_missing_args_is_usage_error():
    try:
        main([])
    except SystemExit as e:  # argparse .error() raises SystemExit(2)
        assert e.code == 2
    else:
        raise AssertionError("expected SystemExit(2)")
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_cli.py -q` → FAIL.

- [ ] **Step 3: Implement** — `src/atv/cli.py`
```python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter

from atv.context import (
    AnalysisContext,
    diff_reconstruct_resolver,
    working_tree_resolver,
)
from atv.detectors import assertion_weakening, force_pass, null_test
from atv.diff import parse_diff
from atv.report import Finding, Severity, to_json, to_text

_DETECTORS = [force_pass.detect, assertion_weakening.detect, null_test.detect]
_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def _run(ctx: AnalysisContext) -> list[Finding]:
    findings: list[Finding] = []
    for det in _DETECTORS:
        try:
            findings.extend(det(ctx))
        except Exception as exc:  # noqa: BLE001 - one detector must not sink the run
            ctx.warnings.append(f"detector {det.__module__} errored: {exc}")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="atv", description="detect faked test/pass signals in a Python diff")
    ap.add_argument("--diff")
    ap.add_argument("--repo")
    ap.add_argument("--base")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on", choices=["low", "medium", "high"], default="low")
    args = ap.parse_args(argv)

    if args.repo and args.base:
        try:
            proc = subprocess.run(
                ["git", "-C", args.repo, "diff", f"{args.base}...HEAD"],
                capture_output=True, text=True, check=False)
        except FileNotFoundError:
            print("error: git not found on PATH", file=sys.stderr)
            return 2
        if proc.returncode != 0:
            # A git failure (bad repo/ref, git missing) must fail loudly — never
            # produce an empty diff that reports a false "clean" and exits 0.
            print(f"error: git diff failed (exit {proc.returncode}): "
                  f"{proc.stderr.strip()}", file=sys.stderr)
            return 2
        files = parse_diff(proc.stdout)
        ctx = AnalysisContext(files, working_tree_resolver(args.repo))
    elif args.diff:
        diff_text = sys.stdin.read() if args.diff == "-" else open(
            args.diff, encoding="utf-8").read()
        files = parse_diff(diff_text)
        ctx = AnalysisContext(files, diff_reconstruct_resolver(files))
    else:
        ap.error("provide --diff <path|-> or --repo <path> --base <ref>")

    findings = _run(ctx)
    summary = {
        "files_analyzed": len(files),
        "skipped_unparseable": len(ctx.warnings),
        "counts_by_pattern": dict(Counter(f.pattern for f in findings)),
    }
    print(json.dumps(to_json(findings, summary), indent=2) if args.json
          else to_text(findings, summary))

    threshold = _ORDER[Severity(args.fail_on)]
    return 1 if any(_ORDER[f.severity] >= threshold for f in findings) else 0
```

- [ ] **Step 4: Run full suite + ruff, verify pass**
Run: `pytest -q && ruff check .`
Expected: all pass; ruff clean. Also manual: `atv --diff tests/fixtures/benchjack_conftest.diff` prints a FLAGGED report and `echo $?` is `1`.

- [ ] **Step 5: Commit**
```bash
git add src/atv/cli.py tests/test_cli.py
git commit -m "feat: CLI (--diff / --repo modes, json, exit codes) + e2e tests"
```

---

### Task 9: README with the demo

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only). This is the distribution artifact — the `conftest.py`-catch demo is the marketing.

- [ ] **Step 1: Write the README** — `README.md`
Include, verbatim and runnable: the one-liner; a "The problem" paragraph (coding agents fake green — the 10-line `conftest.py` all-pass hack); "Install" (`pip install -e .`); a **"Demo"** block showing `atv --diff tests/fixtures/benchjack_conftest.diff` and its FLAGGED output; "What it detects" (the three patterns); "Use in CI" (exit-code note; GitHub Action "coming in v1.1"); "Limitations" (Python-only, static, `--diff`-only mode reconstructs AST for added files only); MIT license line.

- [ ] **Step 2: Verify the demo command in the README actually runs and matches**
Run: `atv --diff tests/fixtures/benchjack_conftest.diff`
Expected: output matches the README's demo block (FLAGGED, `force_pass_hook`, `conftest.py:1`).

- [ ] **Step 3: Commit**
```bash
git add README.md
git commit -m "docs: README with the BenchJack conftest demo"
```

---

## Notes for the implementer

- **Import style:** absolute imports rooted at `atv` (e.g. `from atv.report import Finding`); `pyproject.toml` sets `pythonpath = ["src"]` so `pytest` and `pip install -e .` both resolve it.
- **`ruff check .` must stay clean every task.** The only pre-authorized noqa is `BLE001` on the detector-isolation `except Exception` in `cli.py` (already annotated).
- **Determinism:** no detector may run code, hit the network, or call an LLM. If a detector needs the new file content it must go through `ctx.tree()` / `ctx.new_source()`.
- **Detector isolation:** `cli._run` already guarantees one detector's exception cannot sink the others — do not remove that guard.
