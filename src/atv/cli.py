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
from atv.report import (
    SEVERITY_RANK,
    Finding,
    Severity,
    to_github,
    to_json,
    to_markdown,
    to_text,
)

_DETECTORS = [force_pass.detect, assertion_weakening.detect, null_test.detect]


def _changed_line_count(diff_text: str) -> int:
    """+/- change lines in a raw unified diff (excluding +++/--- file headers)."""
    n = 0
    for ln in diff_text.splitlines():
        if ln.startswith("+") and not ln.startswith("+++"):
            n += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            n += 1
    return n


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
    ap.add_argument("--json", action="store_true",
                    help="deprecated alias for --format json")
    ap.add_argument("--format", choices=["text", "json", "github", "markdown"],
                    default=None,
                    help="output format (default: text; --json implies json)")
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
            # A git failure (bad repo/ref, git missing) must fail loudly - never
            # produce an empty diff that reports a false "clean" and exits 0.
            print(f"error: git diff failed (exit {proc.returncode}): "
                  f"{proc.stderr.strip()}", file=sys.stderr)
            return 2
        files = parse_diff(proc.stdout)
        ctx = AnalysisContext(files, working_tree_resolver(args.repo))
    elif args.diff:
        try:
            if args.diff == "-":
                diff_text = sys.stdin.read()
            else:
                with open(args.diff, encoding="utf-8") as fh:
                    diff_text = fh.read()
        except OSError as exc:
            print(f"error: cannot read diff '{args.diff}': {exc}", file=sys.stderr)
            return 2
        try:
            files = parse_diff(diff_text)
        except Exception as exc:  # noqa: BLE001 - a malformed diff must not crash
            print(f"error: could not parse diff: {exc}", file=sys.stderr)
            return 2
        if _changed_line_count(diff_text) > sum(
                len(f.added_lines) + len(f.removed_lines) for f in files):
            print("error: diff appears malformed (change lines were dropped during "
                  "parsing) - refusing to report a possibly-false 'clean'",
                  file=sys.stderr)
            return 2
        ctx = AnalysisContext(files, diff_reconstruct_resolver(files))
    else:
        ap.error("provide --diff <path|-> or --repo <path> --base <ref>")

    findings = _run(ctx)
    for warning in ctx.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    summary = {
        "files_analyzed": len(files),
        "skipped_unparseable": len(ctx.warnings),
        "counts_by_pattern": dict(Counter(f.pattern for f in findings)),
    }
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
