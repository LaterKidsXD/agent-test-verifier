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
        for text in fd.removed_lines:
            if _ASSERT.match(text):
                findings.append(Finding(
                    fd.path, 0, "assertion_removed", Severity.HIGH,
                    "an assertion was deleted from an existing test", text.strip()))
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
