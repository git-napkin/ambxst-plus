"""Create / search-replace / delete with fuzzy matching and preview."""

from __future__ import annotations

import difflib
from pathlib import Path

from . import diff_validation as dv
from .io_result import FOUND, NOT_FOUND, read_file, write_file
from .registry import Tool
from ..execution_profile import ASK, DENY, can_write_files, decision_to_autoexecute


def parse_edits(args):
    raw = []
    if not args:
        return raw
    if isinstance(args.get("edits"), list):
        raw = args["edits"]
    elif isinstance(args.get("files"), list):
        raw = args["files"]
    elif args.get("file"):
        raw = [args]
    parsed = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = item.get("file") or item.get("path") or item.get("name") or ""
        op = item.get("op") or item.get("type")
        if item.get("delete") is True or op in ("delete", "Delete"):
            parsed.append({"kind": "delete", "file": path})
        elif "content" in item and "search" not in item or op in ("create", "Create"):
            parsed.append(
                {
                    "kind": "create",
                    "file": path,
                    "content": item.get("content") or "",
                    "allow_overwrite": bool(item.get("allow_overwrite", False)),
                }
            )
        else:
            parsed.append(
                {
                    "kind": "str_replace",
                    "file": path,
                    "search": item.get("search") or item.get("old") or "",
                    "replace": item.get("replace") if "replace" in item else item.get("new", ""),
                }
            )
    return parsed


def _unified(path, old, new):
    old_lines = old.splitlines(True)
    new_lines = new.splitlines(True)
    return "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=path)
    )


def _apply_str_replaces(content, edits, file_label):
    deltas = []
    errors = []
    noops = []
    block_index = 0
    for edit in edits:
        block_index += 1
        search = edit["search"]
        replace = edit["replace"]
        span, err, _expected, cleaned = dv.find_search_span(content, search)
        if err:
            errors.append(dv.error_search_mismatch(file_label, block_index))
            continue
        start, end, window = span
        cleaned_replace, _ = dv.remove_extra_line_num_prefix(replace)
        cleaned_replace = dv.append_unmatched_line_suffix(cleaned, cleaned_replace, window)
        if dv.is_noop(cleaned, cleaned_replace, window=window):
            noops.append(dv.error_already_made(file_label))
            continue
        deltas.append({"start": start, "end": end, "replacement": cleaned_replace, "block": block_index})
    kept = dv.deduplicate_overlapping_deltas(deltas)
    new_content = dv.apply_deltas(content, kept) if kept else content
    return new_content, errors, noops, kept


def preprocess_edits(ctx, args):
    edits = parse_edits(args)
    by_file = {}
    for edit in edits:
        by_file.setdefault(edit["file"], []).append(edit)
    previews = []
    errors = []
    planned = []
    for file_name, file_edits in by_file.items():
        abs_path = ctx.resolve_path(file_name)
        kinds = {e["kind"] for e in file_edits}
        if "delete" in kinds:
            io = read_file(abs_path)
            if io.status == NOT_FOUND:
                errors.append(dv.error_missing_file(file_name))
                continue
            old = io.content if io.found else ""
            planned.append({"kind": "delete", "file": file_name, "path": str(abs_path)})
            previews.append(
                {
                    "file": file_name,
                    "unified_diff": _unified(file_name, old, ""),
                    "kind": "delete",
                }
            )
            continue
        if kinds == {"create"} or ("create" in kinds and not abs_path.exists()):
            create = next(e for e in file_edits if e["kind"] == "create")
            if abs_path.exists() and not create.get("allow_overwrite"):
                errors.append("%s already exists." % file_name)
                continue
            old = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
            planned.append(
                {
                    "kind": "create",
                    "file": file_name,
                    "path": str(abs_path),
                    "content": create["content"],
                }
            )
            previews.append(
                {
                    "file": file_name,
                    "unified_diff": _unified(file_name, old, create["content"]),
                    "kind": "create",
                }
            )
            continue
        io = read_file(abs_path)
        if io.status != FOUND:
            errors.append(dv.error_missing_file(file_name))
            continue
        replaces = [e for e in file_edits if e["kind"] == "str_replace"]
        new_content, hunk_errors, noops, kept = _apply_str_replaces(io.content, replaces, file_name)
        if hunk_errors:
            errors.extend(hunk_errors)
            continue
        if noops and not kept:
            errors.extend(noops)
            continue
        planned.append(
            {
                "kind": "str_replace",
                "file": file_name,
                "path": str(abs_path),
                "content": new_content,
            }
        )
        previews.append(
            {
                "file": file_name,
                "unified_diff": _unified(file_name, io.content, new_content),
                "kind": "str_replace",
            }
        )
    return {"previews": previews, "errors": errors, "planned": planned, "edits": edits}


def apply_file_diffs(ctx, args, write=True):
    prepared = preprocess_edits(ctx, args)
    if prepared["errors"] and not prepared["planned"]:
        return {
            "status": "error",
            "error": prepared["errors"][0],
            "errors": prepared["errors"],
            "previews": prepared["previews"],
        }
    if not write:
        return {
            "status": "preview",
            "previews": prepared["previews"],
            "edits": prepared["edits"],
            "errors": prepared["errors"],
        }
    applied = []
    for item in prepared["planned"]:
        path = Path(item["path"])
        if item["kind"] == "delete":
            if path.exists():
                path.unlink()
            applied.append(item["file"])
        else:
            write_file(path, item["content"])
            applied.append(item["file"])
    result = {
        "status": "ok" if not prepared["errors"] else "error",
        "applied": applied,
        "previews": prepared["previews"],
        "errors": prepared["errors"],
    }
    if prepared["errors"]:
        result["error"] = prepared["errors"][0]
    return result


class ApplyFileDiffsTool(Tool):
    name = "apply_file_diffs"
    user_friendly_name = "Edit files"
    schema = {
        "description": "Apply search/replace, create, or delete edits. Prefer this over rewriting whole files.",
        "parameters": {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "search": {"type": "string"},
                            "replace": {"type": "string"},
                            "content": {"type": "string"},
                            "allow_overwrite": {"type": "boolean"},
                            "delete": {"type": "boolean"},
                        },
                        "required": ["file"],
                    },
                }
            },
            "required": ["edits"],
        },
    }

    def should_autoexecute(self, ctx, args):
        decisions = []
        for edit in parse_edits(args):
            decisions.append(can_write_files(ctx.resolve_path(edit["file"]), ctx))
        if not decisions:
            return "deny"
        if any(d == DENY for d in decisions):
            return "deny"
        if any(d == ASK for d in decisions):
            return "ask"
        return True

    def preprocess(self, ctx, args):
        return preprocess_edits(ctx, args)

    def preview(self, ctx, args):
        return apply_file_diffs(ctx, args, write=False)

    def execute(self, ctx, args):
        return apply_file_diffs(ctx, args, write=True)
