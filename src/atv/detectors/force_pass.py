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
        tree = ctx.tree(fd.path) if fd.path.endswith(".py") else None
        if tree is None:
            for ln, text in fd.added_lines:
                for hook in _HOOKS:
                    if f"def {hook}" in text:
                        findings.append(Finding(
                            fd.path, ln, "force_pass_hook", Severity.HIGH,
                            f"pytest hook '{hook}' added - can override test outcomes",
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
                    f"pytest hook '{node.name}' added - can force-pass/deselect tests",
                    f"def {node.name}(...)"))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name == "exit" and node.lineno in added:
                    findings.append(Finding(
                        fd.path, node.lineno, "collection_exit", Severity.HIGH,
                        "module-level exit() in config - can short-circuit collection",
                        "exit(...)"))
    return findings
