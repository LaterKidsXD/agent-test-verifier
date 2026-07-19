from __future__ import annotations

from dataclasses import dataclass, field

from unidiff import PatchSet

_CONFIG_BASENAMES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}


def classify(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    if base in _CONFIG_BASENAMES:
        return "config"
    if (base.startswith("test_") and base.endswith(".py")) or base.endswith("_test.py"):
        return "test"
    if path.startswith("tests/") or "/tests/" in f"/{path}":
        return "test"
    if path.endswith(".py"):
        return "source"
    return "other"


@dataclass
class FileDiff:
    path: str
    status: str
    added_lines: list[tuple[int, str]] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    kind: str = "other"


def parse_diff(diff_text: str) -> list[FileDiff]:
    out: list[FileDiff] = []
    for pf in PatchSet(diff_text):
        path = pf.path
        if pf.is_added_file:
            status = "added"
        elif pf.is_removed_file:
            status = "removed"
        else:
            status = "modified"
        added: list[tuple[int, str]] = []
        removed: list[str] = []
        for hunk in pf:
            for line in hunk:
                text = line.value.rstrip("\n")
                if line.is_added:
                    added.append((line.target_line_no, text))
                elif line.is_removed:
                    removed.append(text)
        out.append(FileDiff(path=path, status=status, added_lines=added,
                            removed_lines=removed, kind=classify(path)))
    return out
