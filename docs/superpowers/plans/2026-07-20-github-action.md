# GitHub Action (v1.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the v1.1 GitHub Action: two new pure CLI output formats (`github` annotations, `markdown` summary), a composite `action.yml`, a dogfooding self-check workflow, README docs, and the 0.1.0 → 1.0.0 version bump.

**Architecture:** Two pieces per the approved spec (`docs/superpowers/specs/2026-07-20-github-action-design.md`). Piece 1: two new pure renderers in `src/atv/report.py` beside `to_text`/`to_json`, wired via a `--format {text,json,github,markdown}` CLI flag (`--json` kept as a back-compat alias). Piece 2: a thin composite `action.yml` (setup-python → pip install from the action's own checkout → resolve base → gate → annotations + summary → exit with the gate's code) plus `.github/workflows/self-check.yml` dogfooding it.

**Tech Stack:** Python 3.11, argparse, pytest, ruff, GitHub composite action (bash), hatchling.

## Global Constraints

- **Work happens on branch `feature/github-action`** (created off `master` in Setup below). NEVER commit to `master`.
- **Repo root:** `D:\bots\agent-test-verifier` (Windows). Run all commands from there.
- **Test command:** `.\.venv\Scripts\python.exe -m pytest -q` — baseline is **39 passed**; it must never drop below that.
- **Lint command:** `.\.venv\Scripts\python.exe -m ruff check .` — must stay "All checks passed!" at every commit.
- **Commit author (pseudonymity, non-negotiable):** repo-local git config is already `LaterKidsXD <250912216+LaterKidsXD@users.noreply.github.com>`. After EVERY commit run `git log -1 --format="%an <%ae>"` and verify exactly that identity. No real name or personal email anywhere — code, YAML, README, commit metadata.
- **`.superpowers/` is git-ignored scratch — never `git add` it.** `docs/superpowers/` IS committed (established repo pattern).
- **No new runtime dependencies.** `pyproject.toml` `dependencies` stays `["unidiff>=0.7.5"]`. (Task 4 installs `pyyaml` into the local venv as a dev-only validation aid — it is NOT added to `pyproject.toml`.)
- **Back-compat is a hard contract:** `--json` keeps working, the JSON schema is unchanged, exit codes stay `0` (clean) / `1` (findings at/above `--fail-on`) / `2` (usage/git/parse error).
- **Non-ASCII note:** `to_markdown` intentionally uses `—` (em-dash) and `·` (middot) — the spec mandates that exact copy and the output renders in a browser (`$GITHUB_STEP_SUMMARY`), not a terminal. Do NOT "fix" it to ASCII. The terminal renderer `to_text` stays ASCII and unchanged.
- **Version bump to `1.0.0` happens ONLY in Task 5** (keep earlier commits at 0.1.0).

## Setup (before Task 1)

```powershell
cd D:\bots\agent-test-verifier
git checkout master
git checkout -b feature/github-action
```

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/atv/report.py` | modify | add `SEVERITY_RANK`, `_esc_data`/`_esc_prop`/`_md_cell` helpers, `to_github()` (Task 1), `to_markdown()` (Task 2) |
| `tests/test_report.py` | modify | unit tests for both renderers (Tasks 1–2) |
| `src/atv/cli.py` | modify | `--format` flag, `--json` alias, dispatch to renderers, reuse `SEVERITY_RANK` (Task 3) |
| `tests/test_cli.py` | modify | end-to-end format tests + alias + usage-error tests (Task 3) |
| `action.yml` | create | composite action (Task 4) |
| `.github/workflows/self-check.yml` | create | dogfood workflow (Task 4) |
| `README.md` | modify | `--format` docs + "Use in CI" GitHub Action section (Task 5) |
| `pyproject.toml` | modify | version `0.1.0` → `1.0.0` (Task 5) |

---

### Task 1: `to_github` renderer in `src/atv/report.py`

**Files:**
- Modify: `src/atv/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: existing `Finding` dataclass and `Severity` enum in `src/atv/report.py`.
- Produces: `SEVERITY_RANK: dict[Severity, int]` (module-level, public — Task 3's CLI imports it) and `to_github(findings: list[Finding], fail_on: Severity) -> str` (newline-joined annotation lines; `""` for no findings — Task 3 dispatches to it).

Renderer contract (from the spec):
- One [workflow-command](https://docs.github.com/actions/using-workflows/workflow-commands-for-github-actions) annotation per finding: `::error file=<f>,line=<n>,title=atv%3A <pattern>::<message>`.
- Threshold-aware level: severity **at or above** `fail_on` → `::error`; below → `::warning`.
- `line == 0` (net-deleted assertions — `assertion_removed` findings carry line `0`) → file-level annotation: omit the `line=` property entirely.
- Escaping — message channel (command data): `%`→`%25`, `\r`→`%0D`, `\n`→`%0A`. Property values (`file`, `title`): those three PLUS `:`→`%3A`, `,`→`%2C`. `%` must be escaped FIRST in both (else the escapes get double-escaped).
- Empty findings → `""`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_report.py`:

```python
from atv.report import to_github


def test_to_github_annotation_shape():
    fs = [Finding("t/test_x.py", 12, "null_test", Severity.HIGH, "asserts nothing")]
    out = to_github(fs, fail_on=Severity.LOW)
    assert out == (
        "::error file=t/test_x.py,line=12,title=atv%3A null_test::asserts nothing")


def test_to_github_error_at_or_above_threshold_warning_below():
    fs = [
        Finding("a.py", 1, "force_pass_hook", Severity.HIGH, "m1"),
        Finding("b.py", 2, "test_skipped", Severity.LOW, "m2"),
    ]
    lines = to_github(fs, fail_on=Severity.MEDIUM).splitlines()
    assert lines[0].startswith("::error ")
    assert lines[1].startswith("::warning ")


def test_to_github_threshold_equal_severity_is_error():
    fs = [Finding("a.py", 1, "p", Severity.MEDIUM, "m")]
    assert to_github(fs, fail_on=Severity.MEDIUM).startswith("::error ")


def test_to_github_escapes_message_and_properties():
    fs = [Finding("dir:a,b/f.py", 3, "p", Severity.HIGH, "100% bad\r\nnext: x,y")]
    out = to_github(fs, fail_on=Severity.LOW)
    # property channel: %, \r, \n AND : , are escaped
    assert "file=dir%3Aa%2Cb/f.py" in out
    # message channel: %, \r, \n escaped but : and , stay literal
    assert out.endswith("::100%25 bad%0D%0Anext: x,y")


def test_to_github_line_zero_is_file_level():
    fs = [Finding("t/test_x.py", 0, "assertion_removed", Severity.MEDIUM, "gone")]
    out = to_github(fs, fail_on=Severity.LOW)
    assert "line=" not in out
    assert "file=t/test_x.py,title=" in out


def test_to_github_empty_findings_is_empty():
    assert to_github([], fail_on=Severity.LOW) == ""
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_report.py -q`
Expected: ImportError — `cannot import name 'to_github'`.

- [ ] **Step 3: Implement** — append to `src/atv/report.py`:

```python
SEVERITY_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def _esc_data(s: str) -> str:
    """Escape the workflow-command message channel ('%' first, always)."""
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _esc_prop(s: str) -> str:
    """Escape a workflow-command property value (file=, title=)."""
    return _esc_data(s).replace(":", "%3A").replace(",", "%2C")


def to_github(findings: list[Finding], fail_on: Severity) -> str:
    lines = []
    for f in findings:
        level = ("error" if SEVERITY_RANK[f.severity] >= SEVERITY_RANK[fail_on]
                 else "warning")
        props = [f"file={_esc_prop(f.file)}"]
        if f.line != 0:
            props.append(f"line={f.line}")
        props.append(f"title={_esc_prop(f'atv: {f.pattern}')}")
        lines.append(f"::{level} {','.join(props)}::{_esc_data(f.message)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the full gate to verify green**

Run: `.\.venv\Scripts\python.exe -m pytest -q` — Expected: **45 passed** (39 + 6).
Run: `.\.venv\Scripts\python.exe -m ruff check .` — Expected: All checks passed!

- [ ] **Step 5: Commit**

```powershell
git add src/atv/report.py tests/test_report.py
git commit -m "feat: add GitHub workflow-command annotation renderer (to_github)"
git log -1 --format="%an <%ae>"   # MUST print: LaterKidsXD <250912216+LaterKidsXD@users.noreply.github.com>
```

---

### Task 2: `to_markdown` renderer in `src/atv/report.py`

**Files:**
- Modify: `src/atv/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `Finding`, `Severity` (existing).
- Produces: `to_markdown(findings: list[Finding], summary: dict) -> str` — same `summary` dict shape the other renderers receive (`files_analyzed`, `skipped_unparseable`, `counts_by_pattern`). No trailing newline (CLI's `print` adds it). Task 3 dispatches to it.

Renderer contract (from the spec — copy is exact, including `—` and `·`):
- Flagged: `### agent-test-verifier — FLAGGED (N finding(s))`, blank line, `M file(s) analyzed · counts: \`pat\` n, ...`, blank line, then a `| Severity | File | Line | Pattern | Message |` table, one row per finding.
- Clean: `### agent-test-verifier — clean`, blank line, `M file(s) analyzed, no faked-green patterns found.`
- Cell escaping: `|`→`\|`; any newline (`\r\n`, `\n`, `\r`) collapses to a single space — one finding must never break the table.
- The `Line` cell emits `f.line` as-is (the spec special-cases line 0 only in the github renderer — YAGNI here).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_report.py`:

```python
from atv.report import to_markdown


def test_to_markdown_flagged_table():
    fs = [
        Finding("tests/conftest.py", 3, "force_pass", Severity.HIGH,
                "hook overrides outcome"),
        Finding("tests/test_x.py", 12, "null_test", Severity.LOW,
                "no meaningful assertion"),
    ]
    summary = {"files_analyzed": 3, "skipped_unparseable": 0,
               "counts_by_pattern": {"force_pass": 1, "null_test": 1}}
    out = to_markdown(fs, summary)
    assert "### agent-test-verifier — FLAGGED (2 finding(s))" in out
    assert "3 file(s) analyzed · counts: `force_pass` 1, `null_test` 1" in out
    assert "| Severity | File | Line | Pattern | Message |" in out
    assert "|---|---|---|---|---|" in out
    assert ("| high | tests/conftest.py | 3 | force_pass "
            "| hook overrides outcome |") in out
    assert ("| low | tests/test_x.py | 12 | null_test "
            "| no meaningful assertion |") in out


def test_to_markdown_escapes_cells():
    fs = [Finding("a.py", 1, "p", Severity.HIGH, "bad | pipe\nand newline")]
    summary = {"files_analyzed": 1, "skipped_unparseable": 0,
               "counts_by_pattern": {"p": 1}}
    assert "bad \\| pipe and newline" in to_markdown(fs, summary)


def test_to_markdown_clean():
    summary = {"files_analyzed": 3, "skipped_unparseable": 0,
               "counts_by_pattern": {}}
    out = to_markdown([], summary)
    assert "### agent-test-verifier — clean" in out
    assert "3 file(s) analyzed, no faked-green patterns found." in out
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_report.py -q`
Expected: ImportError — `cannot import name 'to_markdown'`.

- [ ] **Step 3: Implement** — append to `src/atv/report.py`:

```python
def _md_cell(s: str) -> str:
    """Escape a Markdown table cell so one finding can't break the table."""
    s = s.replace("|", "\\|")
    return s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def to_markdown(findings: list[Finding], summary: dict) -> str:
    if not findings:
        return (
            "### agent-test-verifier — clean\n\n"
            f"{summary['files_analyzed']} file(s) analyzed, "
            "no faked-green patterns found."
        )
    counts = ", ".join(
        f"`{p}` {n}" for p, n in summary["counts_by_pattern"].items())
    out = [
        f"### agent-test-verifier — FLAGGED ({len(findings)} finding(s))",
        "",
        f"{summary['files_analyzed']} file(s) analyzed · counts: {counts}",
        "",
        "| Severity | File | Line | Pattern | Message |",
        "|---|---|---|---|---|",
    ]
    for f in findings:
        out.append(
            f"| {f.severity.value} | {_md_cell(f.file)} | {f.line} "
            f"| {_md_cell(f.pattern)} | {_md_cell(f.message)} |")
    return "\n".join(out)
```

- [ ] **Step 4: Run the full gate to verify green**

Run: `.\.venv\Scripts\python.exe -m pytest -q` — Expected: **48 passed** (45 + 3).
Run: `.\.venv\Scripts\python.exe -m ruff check .` — Expected: All checks passed!

- [ ] **Step 5: Commit**

```powershell
git add src/atv/report.py tests/test_report.py
git commit -m "feat: add markdown step-summary renderer (to_markdown)"
git log -1 --format="%an <%ae>"   # MUST print: LaterKidsXD <250912216+LaterKidsXD@users.noreply.github.com>
```

---

### Task 3: widen `--json` to `--format {text,json,github,markdown}` in `src/atv/cli.py`

**Files:**
- Modify: `src/atv/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `to_github(findings, fail_on: Severity)`, `to_markdown(findings, summary)`, `SEVERITY_RANK` from `atv.report` (Tasks 1–2).
- Produces: the CLI contract Task 4's `action.yml` shells out to — `atv --repo <p> --base <ref> --fail-on <sev> --format github|markdown`, exit codes unchanged (`0`/`1`/`2`).

Behavior contract:
- `--format` choices `{text,json,github,markdown}`; when absent, `--json` selects `json`, else `text`. An explicit `--format` wins over `--json` (the alias only fills the default).
- The resolved `--fail-on` `Severity` is passed into `to_github` (threshold-aware error/warning) AND still drives the exit code exactly as before.
- `--format github` with zero findings prints **nothing** (not even a blank line).
- Unknown `--format` value → argparse usage error → `SystemExit(2)`.
- The local `_ORDER` dict in `cli.py` is replaced by `SEVERITY_RANK` imported from `atv.report` (DRY — single severity ordering).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_cli.py`:

```python
def test_format_github_emits_error_annotation(capsys):
    rc = main(["--diff", "tests/fixtures/benchjack_conftest.diff",
               "--format", "github"])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("::error ")
    assert "file=conftest.py" in out
    assert "title=atv%3A force_pass_hook" in out


def test_format_github_clean_diff_prints_nothing(tmp_path, capsys):
    p = tmp_path / "clean.diff"
    p.write_text(
        "diff --git a/tests/test_a.py b/tests/test_a.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/tests/test_a.py\n"
        "@@ -0,0 +1,2 @@\n+def test_a():\n+    assert 1 + 1 == 2\n"
    )
    rc = main(["--diff", str(p), "--format", "github"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_format_github_below_threshold_warns_and_passes(tmp_path, capsys):
    # test_skipped is MEDIUM; with --fail-on high it must warn, not fail
    p = tmp_path / "skip.diff"
    p.write_text(
        "diff --git a/tests/test_s.py b/tests/test_s.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/tests/test_s.py\n"
        "@@ -0,0 +1,3 @@\n+@pytest.mark.skip\n+def test_s():\n"
        "+    assert 1 + 1 == 2\n"
    )
    rc = main(["--diff", str(p), "--format", "github", "--fail-on", "high"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("::warning ")
    assert "test_skipped" in out


def test_format_markdown_flagged(capsys):
    rc = main(["--diff", "tests/fixtures/benchjack_conftest.diff",
               "--format", "markdown"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "### agent-test-verifier — FLAGGED" in out
    assert "| high | conftest.py | 1 | force_pass_hook |" in out


def test_json_flag_is_alias_for_format_json(capsys):
    rc1 = main(["--diff", "tests/fixtures/benchjack_conftest.diff", "--json"])
    out1 = capsys.readouterr().out
    rc2 = main(["--diff", "tests/fixtures/benchjack_conftest.diff",
                "--format", "json"])
    out2 = capsys.readouterr().out
    assert (rc1, out1) == (rc2, out2)


def test_invalid_format_is_usage_error():
    try:
        main(["--diff", "tests/fixtures/benchjack_conftest.diff",
              "--format", "yaml"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("expected SystemExit(2)")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli.py -q`
Expected: the four `--format` tests error with `SystemExit(2)` / usage failures (`--format` doesn't exist yet); the alias + invalid-format tests may pass/fail incidentally — what matters is the `--format` tests fail.

- [ ] **Step 3: Implement in `src/atv/cli.py`**

3a. Replace the import line:

```python
from atv.report import Finding, Severity, to_json, to_text
```

with:

```python
from atv.report import (
    SEVERITY_RANK,
    Finding,
    Severity,
    to_github,
    to_json,
    to_markdown,
    to_text,
)
```

3b. Delete the module-level line `_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}` and change its two uses at the end of `main()` (see 3d).

3c. In `main()`, replace:

```python
    ap.add_argument("--json", action="store_true")
```

with:

```python
    ap.add_argument("--json", action="store_true",
                    help="deprecated alias for --format json")
    ap.add_argument("--format", choices=["text", "json", "github", "markdown"],
                    default=None,
                    help="output format (default: text; --json implies json)")
```

3d. Replace the output + exit block at the end of `main()`:

```python
    print(json.dumps(to_json(findings, summary), indent=2) if args.json
          else to_text(findings, summary))

    threshold = _ORDER[Severity(args.fail_on)]
    return 1 if any(_ORDER[f.severity] >= threshold for f in findings) else 0
```

with:

```python
    fail_on = Severity(args.fail_on)
    fmt = args.format or ("json" if args.json else "text")
    if fmt == "json":
        print(json.dumps(to_json(findings, summary), indent=2))
    elif fmt == "github":
        annotations = to_github(findings, fail_on)
        if annotations:
            print(annotations)
    elif fmt == "markdown":
        print(to_markdown(findings, summary))
    else:
        print(to_text(findings, summary))

    threshold = SEVERITY_RANK[fail_on]
    return 1 if any(
        SEVERITY_RANK[f.severity] >= threshold for f in findings) else 0
```

- [ ] **Step 4: Run the full gate to verify green**

Run: `.\.venv\Scripts\python.exe -m pytest -q` — Expected: **54 passed** (48 + 6).
Run: `.\.venv\Scripts\python.exe -m ruff check .` — Expected: All checks passed!

- [ ] **Step 5: Commit**

```powershell
git add src/atv/cli.py tests/test_cli.py
git commit -m "feat: widen --json to --format {text,json,github,markdown} (--json kept as alias)"
git log -1 --format="%an <%ae>"   # MUST print: LaterKidsXD <250912216+LaterKidsXD@users.noreply.github.com>
```

---

### Task 4: composite `action.yml` + `.github/workflows/self-check.yml`

**Files:**
- Create: `action.yml` (repo root)
- Create: `.github/workflows/self-check.yml`

**Interfaces:**
- Consumes: the Task 3 CLI contract (`atv --repo --base --fail-on --format github|markdown`, exit `0`/`1`/`2`).
- Produces: the consumer-facing action (`uses: LaterKidsXD/agent-test-verifier@v1` with inputs `base`, `fail-on`) that Task 5's README documents.

Composite actions cannot be executed locally — validation here is (a) YAML parses, (b) the embedded bash scripts pass `bash -n`, (c) careful review against the spec's exit-code discipline. The real end-to-end test is the self-check run on this repo's PR (noted in the spec, not asserted in pytest).

Correctness notes baked into the YAML below (do not "simplify" them away):
- GitHub runs composite `shell: bash` steps with `bash -e -o pipefail`. `atv` exits `1` on findings, so the gate run uses `|| CODE=$?` (never bare `CODE=$?` after the command, which would abort under `-e`), and the markdown pass gets `|| true` (its findings-exit is redundant — `$CODE` from the github pass is authoritative).
- Exit `2` (git failure / malformed diff) skips the summary pass and propagates — a broken scan must never read as "clean".
- Inputs reach the script via an `env:` block, not inline `${{ }}` interpolation inside `run:` — avoids template injection and keeps the script `bash -n`-checkable.
- `line=0` findings, escaping, and error/warning levels are all handled inside `atv --format github` (Tasks 1/3) — the action adds no output logic of its own.

- [ ] **Step 1: Create `action.yml`** at the repo root with exactly:

```yaml
name: agent-test-verifier
description: >-
  Detect faked test/pass signals (force-pass hooks, neutered assertions,
  null tests) in a pull request diff. Annotates flagged lines inline,
  writes a findings table to the step summary, and gates the check.

inputs:
  base:
    description: >-
      Git ref to diff HEAD against. Defaults to the PR target branch
      (origin/$GITHUB_BASE_REF) on pull_request events; required otherwise.
    required: false
    default: ""
  fail-on:
    description: "Minimum severity that fails the check: low, medium, or high."
    required: false
    default: "low"

runs:
  using: composite
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install agent-test-verifier
      shell: bash
      run: pip install "$GITHUB_ACTION_PATH"

    - name: Run agent-test-verifier
      shell: bash
      env:
        INPUT_BASE: ${{ inputs.base }}
        FAIL_ON: ${{ inputs.fail-on }}
      run: |
        BASE="$INPUT_BASE"
        if [ -z "$BASE" ]; then
          if [ -n "$GITHUB_BASE_REF" ]; then
            git -C "$GITHUB_WORKSPACE" fetch --no-tags origin "$GITHUB_BASE_REF" || true
            BASE="origin/$GITHUB_BASE_REF"
          else
            echo "::error::agent-test-verifier: no 'base' input and not a pull_request event; set the 'base' input."
            exit 2
          fi
        fi
        CODE=0
        atv --repo "$GITHUB_WORKSPACE" --base "$BASE" --fail-on "$FAIL_ON" --format github || CODE=$?
        if [ "$CODE" -eq 2 ]; then
          exit 2
        fi
        atv --repo "$GITHUB_WORKSPACE" --base "$BASE" --fail-on "$FAIL_ON" --format markdown >> "$GITHUB_STEP_SUMMARY" || true
        exit "$CODE"
```

- [ ] **Step 2: Create `.github/workflows/self-check.yml`** with exactly:

```yaml
name: self-check

on:
  pull_request:

permissions:
  contents: read

jobs:
  atv:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # atv diffs against the PR base; full history required
      - uses: ./
```

- [ ] **Step 3: Validate both YAML files parse and the embedded bash is syntactically valid**

```powershell
.\.venv\Scripts\python.exe -m pip install pyyaml   # dev-only; NOT a pyproject dependency
.\.venv\Scripts\python.exe -c "import yaml; a=yaml.safe_load(open('action.yml', encoding='utf-8')); w=yaml.safe_load(open('.github/workflows/self-check.yml', encoding='utf-8')); assert a['runs']['using'] == 'composite'; assert set(a['inputs']) == {'base', 'fail-on'}; assert 'pull_request' in w[True]; open('.superpowers/action-scripts.sh', 'w', newline='\n').write('\n\n'.join(s['run'] for s in a['runs']['steps'] if 'run' in s)); print('yaml ok')"
bash -n .superpowers/action-scripts.sh
```

Expected: `yaml ok`, then `bash -n` exits silently (0). (Note: YAML parses the key `on:` as boolean `True` — that's why the check indexes `w[True]`. Git Bash provides `bash` on this machine.)

- [ ] **Step 4: Run the full gate (unchanged code, but keep the invariant)**

Run: `.\.venv\Scripts\python.exe -m pytest -q` — Expected: **54 passed**.
Run: `.\.venv\Scripts\python.exe -m ruff check .` — Expected: All checks passed!

- [ ] **Step 5: Commit** (do NOT add `.superpowers/`)

```powershell
git add action.yml .github/workflows/self-check.yml
git commit -m "feat: composite GitHub Action + self-check dogfood workflow"
git log -1 --format="%an <%ae>"   # MUST print: LaterKidsXD <250912216+LaterKidsXD@users.noreply.github.com>
```

---

### Task 5: README "Use in CI" section + version bump to 1.0.0

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml` (line 3: `version = "0.1.0"` → `version = "1.0.0"`)

**Interfaces:**
- Consumes: the action published as `LaterKidsXD/agent-test-verifier@v1` (tagged post-merge) and the Task 3 `--format` flag.
- Produces: the consumer-facing docs; the 1.0.0 package version.

- [ ] **Step 1: Update the README "Use in CI" section.** Replace the current section body — everything from the `## Use in CI` heading down to (and including) the paragraph `A GitHub Action wrapper around --repo --base is coming in v1.1 — for now, call the CLI directly from any CI step after checkout.` — with:

````markdown
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
````

(The exit-code list and "Two run modes" block are the existing content, kept verbatim — only the `--json` paragraph and the "coming in v1.1" paragraph are replaced by the `--format` list, and the GitHub Action subsection is new.)

- [ ] **Step 2: Bump the version.** In `pyproject.toml` change `version = "0.1.0"` to `version = "1.0.0"`. (Rationale from the spec: shipping a CI action others pin is a 1.0-level commitment to the `--json`/exit-code contract; "v1.1" was the milestone name, not the package version.)

- [ ] **Step 3: Sanity-check the install path still works with the bumped version**

Run: `.\.venv\Scripts\python.exe -m pip install -e . --quiet; .\.venv\Scripts\atv.exe --diff tests/fixtures/benchjack_conftest.diff --format github`
Expected: one `::error file=conftest.py,line=1,title=atv%3A force_pass_hook::...` line, exit code 1.

- [ ] **Step 4: Run the full gate to verify green**

Run: `.\.venv\Scripts\python.exe -m pytest -q` — Expected: **54 passed**.
Run: `.\.venv\Scripts\python.exe -m ruff check .` — Expected: All checks passed!

- [ ] **Step 5: Commit**

```powershell
git add README.md pyproject.toml
git commit -m "docs: Use in CI (GitHub Action) section; release 1.0.0"
git log -1 --format="%an <%ae>"   # MUST print: LaterKidsXD <250912216+LaterKidsXD@users.noreply.github.com>
```

---

## Post-merge release steps (outside the plan's task loop; run after the branch lands on master)

1. Open a PR for `feature/github-action` → the `self-check.yml` run on that very PR is the end-to-end integration test (the action scanning the PR that adds it; expect **green** — the branch adds no faked-green patterns).
2. Merge to `master`, push.
3. Tag and push the release tags (exact + moving major):

```powershell
git tag v1.0.0
git tag v1
git push origin master v1.0.0 v1
```

4. Success criterion 2's red half (a PR with a planted faked-green pattern goes red with inline annotations) can be demonstrated later with a throwaway PR; not part of this branch.
