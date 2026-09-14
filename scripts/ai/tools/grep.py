"""Locator grep: paths and line numbers only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .registry import GREP_TIMEOUT, Tool
from ..execution_profile import can_read_files, decision_to_autoexecute


def _git_root(path):
    current = Path(path)
    if current.is_file():
        current = current.parent
    probe = current
    for _ in range(64):
        if (probe / ".git").exists():
            return probe
        if probe.parent == probe:
            break
        probe = probe.parent
    return None


def _parse_git_grep(raw):
    results = {}
    if not raw:
        return []
    if b"\0" in raw:
        parts = raw.split(b"\0")
        i = 0
        while i < len(parts):
            chunk = parts[i]
            if not chunk:
                i += 1
                continue
            if i + 1 < len(parts):
                path = chunk.decode("utf-8", errors="replace")
                rest = parts[i + 1].decode("utf-8", errors="replace")
                i += 2
                line_no = None
                if rest[:1].isdigit():
                    num, _, _tail = rest.partition(":")
                    try:
                        line_no = int(num)
                    except ValueError:
                        line_no = None
                if line_no is None and ":" in path:
                    maybe_path, _, maybe_line = path.partition(":")
                    try:
                        line_no = int(maybe_line)
                        path = maybe_path
                    except ValueError:
                        pass
                if line_no is not None:
                    results.setdefault(path, set()).add(line_no)
                continue
            i += 1
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) < 2:
            continue
        path, num = parts[0], parts[1]
        try:
            line_no = int(num)
        except ValueError:
            continue
        results.setdefault(path, set()).add(line_no)
    return [
        {"file_path": path, "matched_lines": [{"line_number": n} for n in sorted(nums)]}
        for path, nums in sorted(results.items())
    ]


def _parse_rg_json(raw):
    results = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data") or {}
        path = ((data.get("path") or {}).get("text")) or ""
        line_no = data.get("line_number")
        if path and line_no:
            results.setdefault(path, set()).add(int(line_no))
    return [
        {"file_path": path, "matched_lines": [{"line_number": n} for n in sorted(nums)]}
        for path, nums in sorted(results.items())
    ]


def _run_argv(argv, cwd, timeout):
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except OSError as exc:
        return None, str(exc)
    if proc.returncode == 0:
        return proc.stdout, None
    if proc.returncode == 1:
        return b"", None
    return None, proc.stderr.decode("utf-8", errors="replace") or "grep failed"


def _python_walk(queries, root, timeout):
    deadline = time.monotonic() + timeout
    results = {}
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv"}
    compiled = queries
    root = Path(root)
    if root.is_file():
        files = [root]
        walk = []
    else:
        files = []
        walk = os.walk(root)

    def consider(path):
        if time.monotonic() > deadline:
            return False
        try:
            with open(path, "rb") as fh:
                sample = fh.read(8192)
            if b"\0" in sample:
                return True
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return True
        rel = str(path)
        try:
            rel = str(Path(path).resolve().relative_to(root.resolve() if root.is_dir() else root.parent.resolve()))
        except ValueError:
            rel = str(path)
        for i, line in enumerate(text.splitlines(), 1):
            for query in compiled:
                if query in line:
                    results.setdefault(rel, set()).add(i)
                    break
        return True

    if files:
        consider(files[0])
    else:
        for dirpath, dirnames, filenames in walk:
            if time.monotonic() > deadline:
                break
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for name in filenames:
                if not consider(Path(dirpath) / name):
                    break
    return [
        {"file_path": path, "matched_lines": [{"line_number": n} for n in sorted(nums)]}
        for path, nums in sorted(results.items())
    ]


def grep(ctx, args):
    queries = list(args.get("queries") or [])
    path = args.get("path") or "."
    if not queries:
        return {"results": []}
    target = ctx.resolve_path(path) if path not in (".", "") else ctx.workspace
    timeout = GREP_TIMEOUT
    git_root = _git_root(target)
    if git_root is not None and shutil.which("git"):
        rel = "."
        try:
            rel = str(target.relative_to(git_root))
        except ValueError:
            rel = str(target)
        argv = ["git", "-C", str(git_root), "grep", "-n", "-I", "-E", "-z", "--full-name"]
        for query in queries:
            argv.extend(["-e", query])
        argv.extend(["--", rel])
        raw, err = _run_argv(argv, git_root, timeout)
        if err is None:
            return {"results": _parse_git_grep(raw)}
    if shutil.which("rg"):
        argv = ["rg", "--json", "--hidden", "--glob", "!.git"]
        for query in queries:
            argv.extend(["-e", query])
        argv.append(str(target))
        raw, err = _run_argv(argv, ctx.workspace, timeout)
        if err is None:
            return {"results": _parse_rg_json(raw)}
    return {"results": _python_walk(queries, target, timeout)}


class GrepTool(Tool):
    name = "grep"
    user_friendly_name = "Grep"
    schema = {
        "description": "Search for queries and return file paths with matching line numbers only. Then read_files those ranges.",
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {"type": "array", "items": {"type": "string"}},
                "path": {"type": "string"},
            },
            "required": ["queries", "path"],
        },
    }

    def should_autoexecute(self, ctx, args):
        path = args.get("path") or "."
        target = ctx.resolve_path(path) if path not in (".", "") else ctx.workspace
        return decision_to_autoexecute(can_read_files(target, ctx))

    def execute(self, ctx, args):
        return grep(ctx, args)
