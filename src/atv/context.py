from __future__ import annotations

import ast
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from atv.diff import FileDiff

Resolver = Callable[[str], "str | None"]


@dataclass
class AnalysisContext:
    files: list[FileDiff]
    resolver: Resolver
    warnings: list[str] = field(default_factory=list)
    _src: dict[str, str | None] = field(default_factory=dict)
    _tree: dict[str, ast.Module | None] = field(default_factory=dict)

    def new_source(self, path: str) -> str | None:
        if path not in self._src:
            self._src[path] = self.resolver(path)
        return self._src[path]

    def tree(self, path: str) -> ast.Module | None:
        if path in self._tree:
            return self._tree[path]
        tree: ast.Module | None = None
        src = self.new_source(path)
        if src is not None:
            try:
                tree = ast.parse(src)
            except SyntaxError:
                self.warnings.append(f"skipped unparseable file: {path}")
        self._tree[path] = tree
        return tree


def working_tree_resolver(repo_root: str) -> Resolver:
    def resolve(path: str) -> str | None:
        try:
            with open(os.path.join(repo_root, path), encoding="utf-8") as fh:
                return fh.read()
        except (OSError, UnicodeDecodeError):
            return None
    return resolve


def diff_reconstruct_resolver(files: list[FileDiff]) -> Resolver:
    by_path = {f.path: f for f in files}

    def resolve(path: str) -> str | None:
        fd = by_path.get(path)
        if fd is None or fd.status != "added":
            return None
        return "\n".join(text for _, text in fd.added_lines)
    return resolve
