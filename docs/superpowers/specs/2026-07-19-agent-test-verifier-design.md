# Agent Test-Faking Detector — Design Spec

**Date:** 2026-07-19
**Status:** Approved design (pre-implementation)
**Working name:** `agent-test-verifier` (public/package name TBD — see Open Questions)

---

## Overview

An open-source tool that catches when a **coding agent fakes its passing signal** — i.e., makes a test suite go green by *cheating* (gaming the tests/config) instead of by writing correct code. It reviews a git diff (an agent's PR/changes) and flags fabricated-green patterns that generic reviewers (CodeRabbit, Greptile) do not check for.

**One-liner:** *"Did your coding agent actually fix the code, or did it just game its own tests?"*

**Why it exists:** as coding agents write more PRs, a distinct failure mode scales with them — the agent produces a *green* signal that is faked (e.g., the SWE-bench-defeating 10-line `conftest.py` that forces every test to report pass). Existing AI reviewers hunt bugs and style; the "did the agent fabricate its passing signal?" check is an unfilled gap and a form of reward-hacking detection.

## Goals (v1)

- Detect the three highest-signal, statically-detectable "faked green" patterns in a Python diff (see Detectors).
- Deterministic: no test execution, no LLM, no network — a finding always points to an exact line and is reproducible.
- Ship as a CLI (`pip install`, run on a diff or a repo+base-ref) that emits a human-readable report **and** machine-readable JSON, plus a CI-friendly exit code.
- Ship public (MIT) with a README whose centerpiece is a live demo catching the canonical `conftest.py` all-pass hack.

## Non-goals (v1 — deferred, listed so they are explicitly out of scope)

- Non-Python languages.
- Dynamic analysis / running the tests / mutation testing.
- LLM-assisted detection of subtle cases (e.g., "expected value hard-coded to match a wrong output").
- Coverage-threshold gaming, CI-YAML gaming (`|| true`, etc.).
- The GitHub Action wrapper (planned v1.1 — the CLI core ships first).
- Any monetization (hosted service, x402 endpoint). Explicitly a *later* decision once there is real usage.

## Detectors (v1)

Each detector is a self-contained unit that consumes the parsed diff context and returns a list of `Finding`s. Concrete patterns:

### 1. ForcePassDetector — config/hooks that make tests pass regardless
Flags additions/edits that override test outcomes:
- A `conftest.py` (or pytest plugin) defining `pytest_runtest_makereport` / `pytest_runtest_logreport` / `pytest_collection_modifyitems` in a way that forces `passed` or deselects/skips broadly.
- A `conftest.py` that monkeypatches the suite or ends collection early (`pytest.exit`, `sys.exit(0)` at import/collection time).
- Example (the canonical hack): a new `conftest.py` whose `pytest_collection_modifyitems` empties or force-passes the collected items.

### 2. AssertionWeakeningDetector — existing tests defanged
Flags diffs that weaken or remove the checks that would fail:
- Assertions **deleted** from existing test files (removed lines beginning with `assert` / `self.assert*` / `pytest.raises`).
- Assertions **neutered**: `assert x == y` → `assert True`, `assert 1`, `assert x or True`, `assert x == x`.
- Previously-running tests newly marked `@pytest.mark.skip` / `xfail`, or commented out / deleted.

### 3. NullTestDetector — new "tests" that assert nothing
Flags newly-added `def test_*` functions (or `unittest` test methods) whose body contains **no meaningful assertion** — only `pass`, prints, or calls-without-asserts (no `assert`, no `pytest.raises`, no `self.assert*`, no recognized assert helper). This is the null-agent / degeneracy check applied to test code: a test that cannot fail is a fabricated signal.

## Architecture

**Static analysis of a unified git diff, Python-first.** Pipeline:

```
diff (stdin / file / repo+base-ref)
   → DiffParser          → structured per-file hunks + file classification (test / config / source)
   → AST layer           → parse NEW version of changed .py files; compare to OLD where a detector needs it
   → Detectors (3)       → each returns Finding[]
   → Reporter            → aggregate → text report + JSON + verdict/exit code
```

Detections split by need: diff-based (deleted assertions), new-file-AST-based (a null test, a force-pass hook), or both. The AST layer parses the *new* content of each changed file once and hands each detector the trees + the diff hunks it needs.

## Components / units (files)

- `src/atv/diff.py` — parse a unified diff into `FileDiff` objects (path, added lines, removed lines, hunks); classify each file as `test` / `config` / `source` / `other` by path heuristics (`test_*.py`, `*_test.py`, `tests/`, `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg`).
- `src/atv/context.py` — `AnalysisContext`: the parsed diff + lazy AST of each changed file's new content (skips unparseable files with a recorded warning). One object passed to every detector.
- `src/atv/detectors/force_pass.py`, `assertion_weakening.py`, `null_test.py` — each exposes `detect(ctx: AnalysisContext) -> list[Finding]`. One responsibility each; independently testable.
- `src/atv/report.py` — `Finding` dataclass (`file`, `line`, `pattern`, `severity`, `message`, optional `snippet`); text + JSON formatters; verdict logic.
- `src/atv/cli.py` — arg parsing, orchestration (run all detectors), output selection (`--json`), exit code.

## Interfaces

**CLI:**
```
atv --diff <path|->               # analyze a unified diff (file or stdin)
atv --repo <path> --base <ref>    # compute the diff vs base ref, then analyze
    [--json]                      # emit JSON instead of text
    [--fail-on <severity>]        # exit non-zero if any finding >= severity (default: any)
```
Exit code: `0` = no findings (clean), `1` = findings at/above `--fail-on` (for CI gating), `2` = usage/parse error.

**JSON output (stable schema):**
```json
{
  "verdict": "flagged" | "clean",
  "findings": [
    {"file": "...", "line": 12, "pattern": "force_pass", "severity": "high",
     "message": "conftest.py force-passes collected tests", "snippet": "..."}
  ],
  "summary": {"files_analyzed": 3, "skipped_unparseable": 0, "counts_by_pattern": {"force_pass": 1}}
}
```

## Error handling

- Unparseable changed `.py` file (syntax error in the new content) → skip that file, record a `skipped_unparseable` warning, never crash.
- Non-Python files → ignored in v1 (not an error).
- Empty diff → `clean` verdict, exit 0.
- Malformed/empty diff input or bad args → exit 2 with a clear message.
- A detector raising unexpectedly → caught, logged as a warning, other detectors still run (one detector must never sink the whole run).

## Testing (TDD)

- **Golden fixtures** under `tests/fixtures/`: real "faked green" diffs — the BenchJack-style `conftest.py` all-pass hack, an assertion-weakening diff, a null-test diff — **plus** clean diffs (legitimate new tests, real assertions) that must NOT be flagged.
- Each detector: positive cases (must flag) + negative cases (must stay silent) — false positives are the reputational risk for a review tool, so negative cases are first-class.
- `diff.py` + `report.py`: unit tests for parsing and JSON-schema stability.
- End-to-end: CLI run over each fixture → asserted verdict + exit code.
- The BenchJack `conftest.py` fixture doubles as the README demo.

## Tech stack

Python (3.11+), stdlib `ast` (+ `libcst` only if needed for robust source-range mapping), `unidiff` or a small hand-rolled parser for unified diffs. Zero heavy/runtime deps. `pytest` + `ruff` gate. MIT license.

## OSS / distribution

Public GitHub repo under the builder handle; README leads with the live `conftest.py`-catch demo (the demo *is* the marketing). Distribution is quality-driven (devs discover + share a tool that catches a real, embarrassing failure mode) — no marketing/network required. GitHub Action wrapper follows in v1.1 as the CI-native install path.

## Success criteria (v1)

1. Catches all three patterns on the golden fixtures, including the BenchJack `conftest.py` hack, with zero false positives on the clean fixtures.
2. `pip install` + CLI runs on a real repo diff and returns a correct verdict + exit code.
3. Shipped public with the demo README.
4. (Signal, not gate) adoption shows up as stars / installs / CI usage.

## Open questions (for spec review)

- **Public name / package name.** Working dir is `agent-test-verifier`. Candidates: `greenwash`, `fakegreen`, `testgate`, `greengate`. Your call — it's the public brand.
- **Diff-parsing dependency:** `unidiff` (small, battle-tested) vs. a hand-rolled parser (zero deps). Leaning `unidiff`; flag if you want zero deps.
