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
