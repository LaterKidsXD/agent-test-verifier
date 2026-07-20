from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    pattern: str
    severity: Severity
    message: str
    snippet: str = ""


def verdict(findings: list[Finding]) -> str:
    return "flagged" if findings else "clean"


def to_json(findings: list[Finding], summary: dict) -> dict:
    return {
        "verdict": verdict(findings),
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "pattern": f.pattern,
                "severity": f.severity.value,
                "message": f.message,
                "snippet": f.snippet,
            }
            for f in findings
        ],
        "summary": summary,
    }


def to_text(findings: list[Finding], summary: dict) -> str:
    if not findings:
        return (
            f"clean - {summary['files_analyzed']} file(s) analyzed, "
            "no faked-green patterns found"
        )
    out = [f"FLAGGED - {len(findings)} finding(s):", ""]
    for f in findings:
        out.append(f"  [{f.severity.value}] {f.file}:{f.line}  {f.pattern}")
        out.append(f"      {f.message}")
        if f.snippet:
            out.append(f"      > {f.snippet}")
    return "\n".join(out)


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
