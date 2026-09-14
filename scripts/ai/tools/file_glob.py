"""Library globber with optional git ls-files backend."""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import time
from pathlib import Path

from .registry import GLOB_TIMEOUT, Tool
from ..execution_profile import can_read_files, decision_to_autoexecute


def _git_root(path):
    current = Path(path)
    probe = current if current.is_dir() else current.parent
    for _ in range(64):
        if (probe / ".git").exists():
            return probe
        if probe.parent == probe:
            break
        probe = probe.parent
    return None


def git_ls_files(root, patterns, timeout):
    argv = ["git", "-C", str(root), "ls-files", "-z", "--"] + list(patterns)
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    paths = [p.decode("utf-8", errors="replace") for p in proc.stdout.split(b"\0") if p]
    return paths


def pathlib_glob(root, patterns, timeout):
    deadline = time.monotonic() + timeout
    root = Path(root)
    found = []
    seen = set()
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv"}
    for pattern in patterns:
        if time.monotonic() > deadline:
            break
        try:
            for match in root.glob(pattern):
                if time.monotonic() > deadline:
                    break
                if match.is_file():
                    rel = str(match.relative_to(root)).replace("\\", "/")
                    if rel not in seen:
                        seen.add(rel)
                        found.append(rel)
        except (OSError, ValueError):
            continue
    if found:
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        if time.monotonic() > deadline:
            break
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/")
            for pattern in patterns:
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
                    if rel not in seen:
                        seen.add(rel)
                        found.append(rel)
                    break
    return found


def file_glob(ctx, args):
    patterns = list(args.get("patterns") or [])
    if not patterns:
        return {"paths": []}
    search_dir = args.get("search_dir") or args.get("path") or ""
    root = ctx.resolve_path(search_dir) if search_dir else ctx.workspace
    timeout = GLOB_TIMEOUT
    git_root = _git_root(root)
    used = "pathlib"
    paths = None
    if git_root is not None and shutil.which("git"):
        rel_patterns = patterns
        listed = git_ls_files(git_root, rel_patterns, timeout)
        if listed is not None:
            used = "git"
            try:
                rel_root = root.resolve().relative_to(git_root.resolve())
                prefix = "" if str(rel_root) == "." else str(rel_root).replace("\\", "/") + "/"
            except ValueError:
                prefix = ""
            filtered = []
            for item in listed:
                norm = item.replace("\\", "/")
                if prefix and not norm.startswith(prefix):
                    continue
                trimmed = norm[len(prefix):] if prefix else norm
                if any(fnmatch.fnmatch(trimmed, pat) or fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(Path(trimmed).name, pat) for pat in patterns):
                    filtered.append(trimmed)
            paths = filtered
    if paths is None:
        used = "pathlib"
        paths = pathlib_glob(root, patterns, timeout)
    return {"paths": paths, "backend": used}


class FileGlobTool(Tool):
    name = "file_glob"
    user_friendly_name = "File glob"
    schema = {
        "description": "Find file paths matching glob patterns. Returns paths only.",
        "parameters": {
            "type": "object",
            "properties": {
                "patterns": {"type": "array", "items": {"type": "string"}},
                "search_dir": {"type": "string"},
            },
            "required": ["patterns"],
        },
    }

    def should_autoexecute(self, ctx, args):
        search_dir = args.get("search_dir") or args.get("path") or ""
        root = ctx.resolve_path(search_dir) if search_dir else ctx.workspace
        return decision_to_autoexecute(can_read_files(root, ctx))

    def execute(self, ctx, args):
        return file_glob(ctx, args)
