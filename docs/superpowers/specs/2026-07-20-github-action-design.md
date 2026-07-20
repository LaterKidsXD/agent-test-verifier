# GitHub Action (v1.1) — Design Spec

**Date:** 2026-07-20
**Status:** Approved design (pre-implementation)
**Builds on:** `2026-07-19-agent-test-verifier-design.md` (the shipped `atv` CLI). This adds the CI-native install path that spec deferred to v1.1.

---

## Overview

A drop-in GitHub Action so any repo gets `agent-test-verifier` on every pull request with ~6 lines of workflow YAML. On each PR the action diffs against the target branch, runs `atv`, and reports faked test/pass signals **three ways**: inline annotations on the exact changed lines, a findings table on the checks Summary page, and a red/green check status (gated by the same exit code the CLI already returns).

**One-liner:** *"Add the check to CI once; every agent PR gets scanned for faked-green patterns, inline on the diff."*

**Why it exists:** the v1 CLI is the engine, but the real adoption path for a review check is CI-native — a maintainer should not have to script `atv` into a workflow by hand. This is the install path that turns the shipped tool into something a repo actually keeps running.

## Goals (v1.1)

- A composite `action.yml` a consumer references as `uses: LaterKidsXD/agent-test-verifier@v1` and wires in ~6 lines.
- Findings surface **inline** on the PR diff (GitHub annotations) **and** as a Markdown table on the checks Summary page.
- The check gates the PR via the CLI's existing exit code (`0`/`1`/`2`); severity threshold is configurable (`fail-on`).
- Install `atv` from the action's own checkout (the tool is not on PyPI).
- Dogfood: the repo runs the action on its own PRs — this is also the end-to-end integration test and the canonical usage example.
- Two new **general-purpose** CLI output formats (`github`, `markdown`) that make the tool more useful in *any* CI, not just this action.

## Non-goals (v1.1 — explicitly out of scope)

- Non-GitHub CI (GitLab/Jenkins/etc.) — but the new `--format` outputs are vendor-neutral enough that those users can wire `atv` in themselves.
- A PR **comment** bot (posting/updating a review comment). Annotations + Summary cover v1.1; a comment bot is a later option.
- Publishing to PyPI or the GitHub Marketplace listing (the action works via `uses:` without a Marketplace listing; listing is a later, optional step).
- Any new detectors or detection changes — this release is purely the CI wrapper + output formats. (Detector work — async-def, CRLF, hard-coded-to-match — stays deferred.)
- Auto-fixing / suppression config (allowlist of files, inline `# atv: ignore`). Later, if demand appears.

## Architecture — two pieces

### Piece 1 — two new output formats in the `atv` CLI

The CLI's `--json` boolean widens into `--format {text,json,github,markdown}` (default `text`). `--json` is **kept as a back-compat alias** for `--format json` (no breaking change to the v1 interface or the JSON contract). The two new renderers live beside `to_text`/`to_json` in `src/atv/report.py` as pure functions — same architecture, and they unit-test the same way.

Rationale for putting these in the CLI (not a bespoke action-only script): the renderers are pure and trivially testable, and GitHub annotation output / a Markdown table are genuinely useful to anyone wiring `atv` into CI. The tool gets more capable; the action stays a thin shell composite with no custom Python to maintain. The JSON schema remains the stable machine seam.

**`--format github`** — emits GitHub [workflow-command](https://docs.github.com/actions/using-workflows/workflow-commands-for-github-actions) annotations, one per finding, to stdout:

```
::error file=<file>,line=<line>,title=atv: <pattern>::<message>
::warning file=<file>,line=<line>,title=atv: <pattern>::<message>
```

- **Threshold-aware level:** a finding **at or above** `--fail-on` emits `::error` (it gates the build → red annotation); a finding **below** `--fail-on` emits `::warning` (informational, does not fail). So the renderer takes the resolved threshold: `to_github(findings, fail_on: Severity) -> str`.
- **`line=0` findings** (net-deleted assertions carry line `0` — no single new-file line): GitHub will not render an inline annotation at line 0, so these emit as **file-level** annotations — omit the `line=` property entirely (`::error file=<file>,title=...::<message>`). Still visible, just pinned to the file rather than a line.
- **Escaping (correctness-critical).** GitHub workflow commands require escaping. In the **message** (command data): `%`→`%25`, `\r`→`%0D`, `\n`→`%0A`. In **property values** (`file`, `title`), additionally: `:`→`%3A`, `,`→`%2C` (plus the message-data escapes). Our messages contain `:` and `,`, and titles contain the pattern name — unescaped, annotations render wrong or split. The renderer escapes both channels correctly. Unit-tested.
- Exit code is unchanged — `--format github` still returns `0`/`1`/`2` exactly as `--format text` does; only stdout differs.

**`--format markdown`** — emits a findings summary block for `$GITHUB_STEP_SUMMARY` (also reusable as a PR-comment body). Shape:

Flagged:
```markdown
### agent-test-verifier — FLAGGED (2 finding(s))

3 file(s) analyzed · counts: `force_pass` 1, `null_test` 1

| Severity | File | Line | Pattern | Message |
|---|---|---|---|---|
| high | tests/conftest.py | 3 | force_pass | hook overrides test outcome to 'passed' |
| low | tests/test_x.py | 12 | null_test | added test has no meaningful assertion |
```

Clean:
```markdown
### agent-test-verifier — clean

3 file(s) analyzed, no faked-green patterns found.
```

- **Cell escaping:** table cells escape `|`→`\|` and collapse any newline in a message to a space, so one finding never breaks the table. Unit-tested.
- `to_markdown(findings, summary) -> str` — pure, given the same `findings` + `summary` dict the other renderers receive.

### Piece 2 — the composite `action.yml` (repo root)

Steps:
1. `actions/setup-python@v5` with `python-version: '3.11'`.
2. `pip install "$GITHUB_ACTION_PATH"` — installs `atv` from the action's own checked-out copy (contains `pyproject.toml` + `src/atv/`). Not PyPI.
3. Run `atv` (single shell step) — resolve base, run the gate, emit annotations + summary, exit with the gate's code.

**Data flow (the run step):**

```
resolve BASE (see below)
  ── atv --repo "$GITHUB_WORKSPACE" --base "$BASE" --fail-on "$FAIL_ON" --format github
        → stdout = annotations (GitHub picks these up inline); capture exit code $CODE
  ── if $CODE == 2:  print nothing more (atv already wrote its error to stderr); exit 2
  ── atv --repo "$GITHUB_WORKSPACE" --base "$BASE" --fail-on "$FAIL_ON" --format markdown
        >> "$GITHUB_STEP_SUMMARY"
  ── exit $CODE          # 0 clean / 1 findings-at-or-above-threshold → check red on 1 or 2
```

Analysis runs twice (once per format). It is deterministic and sub-second (diff parse + regex/AST over changed files, no network/LLM), so the second pass costs nothing and keeps the action a plain shell composite — no intermediate JSON file, no bespoke emitter. The first (`--format github`) run is authoritative for the exit code; the second is skipped when the first errors (`$CODE == 2`).

**Shell exit-code discipline (implementation note):** `atv` returns non-zero (`1`) on findings, which under `set -e`/`pipefail` would abort the composite step before annotations/summary are handled. The run step must NOT let a non-zero `atv` abort it — capture the code explicitly (`atv … --format github; CODE=$?`), do the summary run, then `exit $CODE`. Do not run the two `atv` invocations in a pipe whose failure would be swallowed.

**Base-ref resolution (the run step, before the gate):**

```bash
BASE="${{ inputs.base }}"
if [ -z "$BASE" ]; then
  if [ -n "$GITHUB_BASE_REF" ]; then          # a pull_request event
    git -C "$GITHUB_WORKSPACE" fetch --no-tags origin "$GITHUB_BASE_REF" || true
    BASE="origin/$GITHUB_BASE_REF"
  else
    echo "::error::agent-test-verifier: no 'base' input and not a pull_request event; set the 'base' input."
    exit 2
  fi
fi
```

- On a `pull_request` event, `base` defaults to the target branch (`origin/$GITHUB_BASE_REF`); the defensive `fetch` is a no-op when history is already present.
- The consumer must check out with `fetch-depth: 0` so `origin/<base>` and merge-base exist. Documented in the README snippet.
- `base` input overrides for non-PR triggers (pass any ref/SHA `atv --base` accepts).
- `atv --repo … --base <ref>` runs `git diff <ref>...HEAD` (three-dot / merge-base) — unchanged v1 behavior.

**Inputs (minimal — YAGNI):**

| Input | Default | Meaning |
|---|---|---|
| `base` | `""` (→ derives `origin/$GITHUB_BASE_REF` on PRs) | Git ref to diff `HEAD` against. |
| `fail-on` | `low` | Minimum severity that fails the check (`low`/`medium`/`high`). Matches the CLI. |

No `paths` / `python-version` / suppression inputs in v1.1.

## Components / units (files)

| File | Change | Responsibility |
|---|---|---|
| `src/atv/report.py` | modify | add `to_github(findings, fail_on)` and `to_markdown(findings, summary)` (pure renderers + escaping helpers) |
| `src/atv/cli.py` | modify | replace `--json` bool with `--format {text,json,github,markdown}`; keep `--json` as alias for `--format json`; pass the resolved `fail_on` severity into `to_github` |
| `action.yml` | create | composite action: setup-python → pip install from `$GITHUB_ACTION_PATH` → base-resolve + gate + annotations + summary |
| `.github/workflows/self-check.yml` | create | dogfood: `uses: ./` on the repo's own PRs (integration test + usage example) |
| `README.md` | modify | new **"Use in CI (GitHub Action)"** section with the copy-paste workflow; flip the "coming in v1.1" line to "available" |
| `pyproject.toml` | modify | version bump (see Versioning) |
| `tests/test_report.py` | modify | unit tests for `to_github` (escaping, threshold→error/warning, line=0→file-level, clean case) and `to_markdown` (table, cell escaping, clean case) |
| `tests/test_cli.py` | modify | `--format github`/`--format markdown` end-to-end + `--json` alias still works + invalid `--format` value → exit 2 |

## Error handling

- `atv` exit `2` (git failure / malformed diff — the v1 hardening) propagates: the action prints atv's stderr (already emitted) and exits `2`, skipping the summary run. The check goes red — a broken scan must never read as "clean/pass."
- No base resolvable (no `base` input, not a PR) → `::error` + exit `2`.
- `atv` exit `1` (findings at/above threshold) → annotations + summary written, check red.
- `atv` exit `0` (clean) → a "clean" summary is written, check green.
- Invalid `--format` value → argparse exits `2` (usage error) — the CLI's existing behavior.
- The two `atv` runs are deterministic and identical, so annotations and summary never disagree.

## Versioning / release

- **Label reconciliation:** the v1 spec called this feature milestone "v1.1 (the GitHub Action)"; that is the *milestone name*, not the package version. The **package semver** jumps `0.1.0` → `1.0.0` and the **action tag** is `v1`. "v1.1" in this doc's title = "the milestone after the initial CLI ship," nothing more.
- Package: bump `0.1.0` → **`1.0.0`**. Shipping a CI action that other repos depend on is a 1.0-level commitment to the `--json`/exit-code contract; `--json` stays supported as an alias, so nothing v1 breaks.
- Action tags after merge: exact `v1.0.0` **and** a moving major tag `v1`. Consumers pin `uses: LaterKidsXD/agent-test-verifier@v1`.
- `.superpowers/` stays git-ignored (SDD scratch — not published), as in v1.

## Testing (TDD)

- **`to_github`:** message/property escaping (`%`, `\n`, `\r`, `:`, `,`); a finding at/above `fail_on` → `::error`, below → `::warning`; a `line=0` finding → file-level annotation (no `line=`); empty findings → empty output.
- **`to_markdown`:** flagged → correct header + counts line + one row per finding; `|` and newlines in a message escaped/collapsed; clean → the clean block.
- **CLI:** `--format github` and `--format markdown` produce the renderer output over a fixture and exit with the correct code; `--json` still equals `--format json` (alias); unknown `--format` → exit 2.
- **`action.yml` / `self-check.yml`:** composite actions can't be fully exercised locally; the `self-check.yml` run on this repo's next PR is the end-to-end integration test (annotations appear, summary renders, check gates). Noted, not asserted in pytest.
- Existing 39 tests stay green; ruff clean; test output pristine.

## Success criteria (v1.1)

1. A consumer adds ~6 lines of workflow and gets, on each PR: inline annotations on flagged lines, a Summary table, and a check that goes red on findings (respecting `fail-on`) — green when clean.
2. `self-check.yml` runs green on a clean PR to this repo and red (with visible inline annotations) on a PR that introduces a faked-green pattern.
3. `--format github` / `--format markdown` are documented and usable standalone.
4. `v1` tag published; README "Use in CI" section is copy-paste correct.
5. v1's 39 tests + the new format tests all green; ruff clean.

## Decisions (resolved at design, 2026-07-20)

- **Reporting UX:** inline annotations **+** a `$GITHUB_STEP_SUMMARY` Markdown table (both). (User pick.)
- **Renderers live in the CLI** (`--format github/markdown`), not an action-only script — reusable + unit-testable; `--json` kept as a back-compat alias. (Approved.)
- **Analysis runs twice** (once per format) for a script-free composite — deterministic, sub-second, negligible cost. (Approved.)
- **Action type:** composite (shell), not Docker/JS — no container build, installs the tool from its own checkout.
- **Version:** bump to `1.0.0`; publish moving tag `v1` + exact `v1.0.0`; consumers pin `@v1`.
