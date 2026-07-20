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
                    message=f"test '{node.name}' has no visible assertion in its body - it cannot fail",
                    snippet=f"def {node.name}(...)"))
    return findings
