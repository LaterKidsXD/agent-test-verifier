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
        diff_text = subprocess.run(
            ["git", "-C", args.repo, "diff", f"{args.base}...HEAD"],
            capture_output=True, text=True, check=False).stdout
        files = parse_diff(diff_text)
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
