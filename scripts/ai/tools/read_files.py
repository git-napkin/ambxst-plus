"""Batch ranged file reads with partial success."""

from __future__ import annotations

from .io_result import FOUND, read_file
from .registry import Tool
from ..execution_profile import ASK, DENY, can_read_files


def _locations(args):
    if not args:
        return []
    if args.get("files"):
        return list(args["files"])
    if args.get("locations"):
        return list(args["locations"])
    if args.get("name"):
        return [args]
    return []


def _slice_lines(content, ranges):
    lines = content.splitlines(True)
    total = len(lines)
    if not ranges:
        return content, {"start": 1, "end": total} if total else {"start": 1, "end": 0}, total
    chunks = []
    start = None
    end = None
    for spec in ranges:
        lo = int(spec.get("start") or 1)
        hi = int(spec.get("end") or total)
        lo = max(1, lo)
        hi = min(total, hi)
        if hi < lo:
            continue
        if start is None:
            start = lo
        end = hi
        chunks.append("".join(lines[lo - 1 : hi]))
    text = "".join(chunks)
    return text, {"start": start or 1, "end": end or 0}, total


def read_files(ctx, args):
    files = []
    failed_files = []
    for loc in _locations(args):
        if ctx.cancelled():
            return {"status": "Cancelled", "result": {"variant": "Cancelled"}, "files": files, "failed_files": failed_files}
        name = loc.get("name") or loc.get("file") or loc.get("path") or ""
        if not name:
            failed_files.append({"name": "", "error": "missing file name"})
            continue
        abs_path = ctx.resolve_path(name)
        result = read_file(abs_path)
        if result.status != FOUND:
            failed_files.append(
                {
                    "name": name,
                    "path": str(abs_path),
                    "error": result.error or result.status,
                }
            )
            continue
        content, line_range, line_count = _slice_lines(result.content, loc.get("lines") or [])
        truncated = result.truncated
        if result.truncated:
            content = content
        ctx.add_temporary_file_read_permissions(abs_path)
        files.append(
            {
                "file_name": name,
                "path": str(abs_path),
                "content": content,
                "line_range": line_range,
                "line_count": line_count,
                "truncated": truncated,
            }
        )
    return {"files": files, "failed_files": failed_files}


class ReadFilesTool(Tool):
    name = "read_files"
    user_friendly_name = "Read files"
    schema = {
        "description": "Read one or more files. Prefer line ranges after grep. Returns partial success.",
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "lines": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "start": {"type": "integer"},
                                        "end": {"type": "integer"},
                                    },
                                },
                            },
                        },
                        "required": ["name"],
                    },
                }
            },
            "required": ["files"],
        },
    }

    def should_autoexecute(self, ctx, args):
        decisions = []
        for loc in _locations(args):
            name = loc.get("name") or loc.get("file") or loc.get("path") or ""
            if not name:
                continue
            decisions.append(can_read_files(ctx.resolve_path(name), ctx))
        if not decisions:
            return "deny"
        if any(d == DENY for d in decisions):
            return "deny"
        if any(d == ASK for d in decisions):
            return "ask"
        return True

    def execute(self, ctx, args):
        return read_files(ctx, args)
