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
            f"clean — {summary['files_analyzed']} file(s) analyzed, "
            "no faked-green patterns found"
        )
    out = [f"FLAGGED — {len(findings)} finding(s):", ""]
    for f in findings:
        out.append(f"  [{f.severity.value}] {f.file}:{f.line}  {f.pattern}")
        out.append(f"      {f.message}")
        if f.snippet:
            out.append(f"      > {f.snippet}")
    return "\n".join(out)
