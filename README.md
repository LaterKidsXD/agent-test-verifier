# agent-test-verifier (atv)

Did your coding agent actually fix the code, or did it just game its own tests?

`atv` is a static, deterministic checker that scans a diff for the patterns
coding agents use to fake a passing test suite instead of fixing the
underlying bug.

## The problem

Coding agents are graded on green. Under that pressure, the shortest path to
"done" is sometimes not fixing the code — it's neutering the tests. A
10-line `conftest.py` is all it takes:

```python
def pytest_collection_modifyitems(config, items):
    for item in items:
        item.add_marker("skip")
```

Every test in the suite silently skips. `pytest` exits 0. CI goes green.
Nothing was fixed. This kind of hook, a deleted or trivialized assertion, or
a new test that asserts nothing all produce the same fabricated signal:
passing, but not meaningfully so. `atv` catches these patterns in the diff
before you trust the green.

## Install

```bash
pip install -e .
```

Requires Python 3.11+.

## Demo

BenchJack ships a fixture diff (`tests/fixtures/benchjack_conftest.diff`)
containing exactly the `conftest.py` hack above, added as a new file. Run
`atv` against it:

```
$ atv --diff tests/fixtures/benchjack_conftest.diff
FLAGGED — 1 finding(s):

  [high] conftest.py:1  force_pass_hook
      pytest hook 'pytest_collection_modifyitems' added — can force-pass/deselect tests
      > def pytest_collection_modifyitems(...)
```

Exit code: `1` (findings at/above the fail-on threshold — this is what CI
gates on).

### Live demo (GitHub Action on a real PR)

[PR #2](https://github.com/LaterKidsXD/agent-test-verifier/pull/2) is a
permanently open pull request with one target pattern per detector planted
in its diff. The `agent-test-verifier` check on it shows the whole failure
path live: a red check, inline `::error` annotations on the flagged lines,
and the findings table on the run's Summary page.

## What it detects

Three independent, purely static detectors, all AST- or line-based — none of
them execute code:

- **Force-pass hooks** (`force_pass_hook`, `collection_exit`) — a
  `conftest.py`/`pytest.ini`/`tox.ini`/`setup.cfg`/`pyproject.toml` change
  that adds a pytest hook (`pytest_collection_modifyitems`,
  `pytest_runtest_makereport`, `pytest_runtest_logreport`,
  `pytest_runtest_setup`, `pytest_runtest_call`) or a module-level `exit()`
  call — either can force-pass, skip, or short-circuit collection so tests
  never actually run.
- **Assertion weakening** (`assertion_removed`, `assertion_trivialized`,
  `test_skipped`) — an assertion net-deleted from an existing test (not a
  1-for-1 edit — those stay silent), a newly added assertion that's always
  true (`assert True`, `assert 1`, `assert x or True`) and therefore can
  never fail, or a test newly marked `@skip`/`@xfail`.
- **Null tests** (`null_test`) — a newly added `test_*` function whose body
  contains no `assert` statement and no `assert*`/`raises`/`fail` call, so it
  cannot fail no matter what the code does.

## Use in CI

### GitHub Action

Add one workflow file and every pull request gets scanned: findings appear
as inline annotations on the diff, a findings table lands on the checks
Summary page, and the check goes red when any finding meets the `fail-on`
bar:

```yaml
name: agent-test-verifier
on: pull_request
jobs:
  atv:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # atv diffs against the PR base; full history required
      - uses: LaterKidsXD/agent-test-verifier@v1
```

Inputs (both optional):

| Input | Default | Meaning |
|---|---|---|
| `base` | PR target branch | Git ref to diff `HEAD` against — set it for non-PR triggers |
| `fail-on` | `low` | Minimum severity that fails the check: `low`, `medium`, or `high` |

### Any CI (direct CLI)

`atv` returns a process exit code you can gate on directly — no output
parsing required:

- `0` — clean, no findings
- `1` — findings at or above `--fail-on` (default: any; pass
  `--fail-on low|medium|high` to raise the bar)
- `2` — usage or diff-parse error (never a silent false "clean")

Two run modes:

```bash
# Score a standalone diff file (or stdin with -)
atv --diff path/to.diff

# Score everything on the current branch since it diverged from a base ref
atv --repo /path/to/repo --base main
```

Pick an output format with `--format {text,json,github,markdown}`
(default `text`):

- `text` — the human summary shown in the Demo above
- `json` — machine-readable report (`--json` is kept as a back-compat
  alias)
- `github` — GitHub Actions workflow-command annotations: findings at or
  above `--fail-on` emit `::error`, findings below it emit `::warning`
- `markdown` — a findings table suitable for `$GITHUB_STEP_SUMMARY` or a
  PR comment

## Limitations

- **Python-only.** Detectors understand `pytest` conventions and Python
  syntax; other languages/test runners aren't analyzed.
- **Static analysis only.** `atv` never executes the code or the tests it
  scores — it reasons purely over the diff and the AST of changed files, so
  it can't catch runtime-only or dynamically constructed fakes.
- **`--diff`-only mode reconstructs AST for added files only.** When you
  pass a standalone diff (no working tree), `atv` can only rebuild the full
  source — and therefore get an AST — for files the diff *adds*. For
  modified files it sees only the added/removed lines, so line-based
  detectors still run but AST-based detectors (force-pass hooks in modified
  configs, null tests in modified files) are skipped for that file. Use
  `--repo --base` against a real checkout for full AST coverage on modified
  files.

## License

MIT — see [LICENSE](LICENSE).
