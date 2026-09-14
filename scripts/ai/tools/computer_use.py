"""Native computer-use tools. Policy default is Never."""

from __future__ import annotations

import time

from .registry import Tool
from .friendly import labels
from .native import native_request
from ..execution_profile import ALWAYS_ALLOW, NEVER
from ..computer_use import atspi, coords, doctor, input as cu_input, screenshot as cu_shot, windows as cu_windows

ACTIONS = (
    "screenshot",
    "snapshot",
    "click",
    "scroll",
    "drag",
    "move",
    "type",
    "key",
    "focus",
    "move_window",
    "resize_window",
    "perform_action",
    "set_value",
    "wait",
    "cursor",
)

MUTATING = {
    "click",
    "scroll",
    "drag",
    "move",
    "type",
    "key",
    "focus",
    "move_window",
    "resize_window",
    "perform_action",
    "set_value",
}

WAIT_CAP_MS = 5000


def _error(message):
    return {"status": "error", "error": message}


def _ok(payload=None):
    out = {"status": "ok"}
    if payload:
        out.update(payload)
    return out


def _native(ctx, name, args):
    result = native_request(ctx, name, args)
    if result.get("status") == "Cancelled" or result.get("type") == "tool_result":
        return result
    if result.get("status") == "error":
        return result
    inner = result.get("result")
    if isinstance(inner, dict) and inner.get("error"):
        return _error(inner.get("error"))
    return inner if isinstance(inner, dict) else {"result": inner}


def _maybe_shot(ctx, args, result):
    if not isinstance(result, dict) or result.get("status") == "error":
        return result
    if args.get("screenshot") is False:
        return result
    action = args.get("action")
    if action in ("screenshot", "snapshot", "cursor", "wait"):
        return result
    if action not in MUTATING:
        return result
    shot = _capture(ctx, args, raise_window=False)
    if shot.get("status") != "error":
        result["screenshot"] = {k: v for k, v in shot.items() if k != "image_base64"}
        if shot.get("image_base64"):
            result["image_base64"] = shot["image_base64"]
            result["mime_type"] = shot.get("mime_type") or "image/png"
            result["path"] = shot.get("path")
    return result


def _capture(ctx, args, raise_window=None):
    payload = {
        "action": "screenshot",
        "target": args.get("target"),
        "monitor": args.get("monitor"),
        "address": args.get("address") or args.get("window_id"),
        "full_screen": bool(args.get("full_screen")),
        "raise_window": True if raise_window is None else bool(raise_window),
        "include_cursor": args.get("include_cursor", True),
        "geometry": args.get("geometry"),
    }
    native = _native(ctx, "use_computer", payload)
    if native.get("status") == "error" or native.get("error"):
        return native if native.get("status") else _error(native.get("error") or "screenshot failed")
    path = native.get("path")
    if not path:
        return _error("screenshot produced no file")
    try:
        prepared = cu_shot.prepare_payload(
            path,
            max_width=args.get("max_width"),
            max_height=args.get("max_height"),
            max_bytes=args.get("max_bytes"),
            scale=args.get("scale"),
            fmt=args.get("format") or "png",
            quality=args.get("quality"),
        )
    except Exception as exc:
        return _error(str(exc))
    prepared.update(
        {
            "origin_x": native.get("origin_x") or 0,
            "origin_y": native.get("origin_y") or 0,
            "monitor_scale": native.get("monitor_scale") or 1,
            "monitor": native.get("monitor"),
            "crop_x": native.get("crop_x") or 0,
            "crop_y": native.get("crop_y") or 0,
            "cropped_to_window": bool(native.get("cropped_to_window")),
            "window_title": native.get("window_title"),
            "window_off_screen": native.get("window_off_screen"),
            "source": "grim",
        }
    )
    ctx.computer_use_last_shot = {
        k: prepared[k]
        for k in (
            "scale",
            "origin_x",
            "origin_y",
            "monitor_scale",
            "crop_x",
            "crop_y",
            "coordinate_width",
            "coordinate_height",
        )
        if k in prepared
    }
    return _ok(prepared)


def _window_list(ctx):
    native = _native(ctx, "get_windows", {})
    windows = []
    if isinstance(native, dict):
        windows = native.get("windows") or native.get("result", {}).get("windows") or []
        if not windows and isinstance(native.get("result"), dict):
            windows = native["result"].get("windows") or []
    return [cu_windows.enrich_terminal(dict(w)) for w in windows]


def _resolve_point(ctx, args):
    meta = ctx.computer_use_last_shot or {}
    if args.get("x") is None or args.get("y") is None:
        node, err = atspi.resolve_node(ctx.computer_use_nodes, args)
        if err:
            return None, None, err, node
        if node and node.get("bounds"):
            b = node["bounds"]
            return b["x"] + b["width"] // 2, b["y"] + b["height"] // 2, "", node
        return None, None, "click requires x/y, element_index, or a selector (call snapshot first)", node
    x, y = args.get("x"), args.get("y")
    if args.get("relative") and not meta:
        return None, None, "relative coordinates need a prior screenshot of the target window", None
    if meta:
        lx, ly = coords.preview_to_logical(x, y, meta)
        return lx, ly, "", None
    return int(x), int(y), "", None


class RequestComputerUseTool(Tool):
    name = "request_computer_use"
    user_friendly_name = "Request computer use"
    schema = {
        "description": (
            "Request permission to observe and control the desktop (screenshots, clicks, typing). "
            "Call this before use_computer. Returns a doctor report of available backends."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_summary": {
                    "type": "string",
                    "description": "What you intend to do with the desktop",
                }
            },
            "required": ["task_summary"],
        },
    }

    def should_autoexecute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return "deny"
        if ctx.profile.computer_use == ALWAYS_ALLOW:
            return True
        return "ask"

    def execute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return _error("computer use is disabled")
        native = _native(
            ctx,
            "computer_use_session",
            {"op": "begin", "task_summary": (args or {}).get("task_summary") or ""},
        )
        if native.get("status") == "error" or native.get("error"):
            return native if native.get("status") else _error(native.get("error"))
        if native.get("locked"):
            return _error("computer use is blocked while the session is locked")
        ctx.computer_use_approved = True
        ctx.computer_use_nodes = []
        try:
            atspi_ok = atspi.probe()
        except Exception:
            atspi_ok = False
        report = doctor.doctor_report(native=native, atspi_ok=atspi_ok)
        return _ok({"doctor": report, "task_summary": (args or {}).get("task_summary") or ""})

    def user_friendly_name_for(self, args):
        summary = ((args or {}).get("task_summary") or "").strip()
        if summary:
            return labels(
                "Requesting computer use: %s" % summary,
                "Computer use granted: %s" % summary,
                ask="Allow computer use: %s" % summary,
            )
        return labels("Requesting computer use", "Requested computer use", ask="Allow computer use")


class UseComputerTool(Tool):
    name = "use_computer"
    user_friendly_name = "Use computer"
    schema = {
        "description": (
            "Control the local desktop. Prefer snapshot before clicking. Coordinates are in the "
            "returned image space (coordinate_width x coordinate_height). One primary action per call. "
            "Mutating actions return a follow-up screenshot unless screenshot=false."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(ACTIONS),
                    "description": "Desktop action to perform",
                },
                "actions": {
                    "type": "array",
                    "description": "Optional non-visual sequence (key then type). Ignored if action is set besides wait/key/type.",
                    "items": {"type": "object"},
                },
                "action_summary": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "start_x": {"type": "number"},
                "start_y": {"type": "number"},
                "end_x": {"type": "number"},
                "end_y": {"type": "number"},
                "button": {"type": "string"},
                "click_count": {"type": "integer"},
                "relative": {"type": "boolean"},
                "direction": {"type": "string"},
                "pages": {"type": "number"},
                "text": {"type": "string"},
                "key": {"type": "string"},
                "keys": {"type": "string"},
                "ms": {"type": "integer"},
                "element_index": {"type": "integer"},
                "element_identifier": {"type": "string"},
                "role": {"type": "string"},
                "name": {"type": "string"},
                "states": {"type": "array", "items": {"type": "string"}},
                "value": {"type": "string"},
                "address": {"type": "string"},
                "pid": {"type": "integer"},
                "title": {"type": "string"},
                "class": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "screenshot": {"type": "boolean"},
                "full_screen": {"type": "boolean"},
                "raise_window": {"type": "boolean"},
                "target": {"type": "string"},
                "monitor": {"type": "string"},
                "format": {"type": "string"},
                "max_width": {"type": "integer"},
                "max_height": {"type": "integer"},
                "max_bytes": {"type": "integer"},
            },
            "required": ["action"],
        },
    }

    def should_autoexecute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return "deny"
        if ctx.computer_use_approved or ctx.profile.computer_use == ALWAYS_ALLOW or ctx.autoexecute_any_action:
            return True
        return "ask"

    def execute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return _error("computer use is disabled")
        if not ctx.computer_use_approved and ctx.profile.computer_use != ALWAYS_ALLOW:
            return _error("call request_computer_use first")
        if ctx.profile.computer_use == ALWAYS_ALLOW and not ctx.computer_use_approved:
            native = _native(
                ctx,
                "computer_use_session",
                {"op": "begin", "task_summary": (args or {}).get("action_summary") or "AlwaysAllow"},
            )
            if native.get("status") == "error" or native.get("error"):
                return native if native.get("status") else _error(native.get("error"))
            if native.get("locked"):
                return _error("computer use is blocked while the session is locked")
            ctx.computer_use_approved = True
            ctx.computer_use_nodes = []
        args = args or {}
        batch = args.get("actions") if isinstance(args.get("actions"), list) and not args.get("action") else None
        if batch:
            results = []
            for step in batch:
                if not isinstance(step, dict):
                    return _error("actions[] items must be objects")
                one = self._one(ctx, step)
                results.append(one)
                if one.get("status") == "error":
                    return _error(one.get("error") or "action failed")
            return _ok({"results": results})
        return self._one(ctx, args)

    def _one(self, ctx, args):
        action = str(args.get("action") or "").strip()
        if action not in ACTIONS:
            return _error("unknown action: %s" % (action or "(empty)"))
        if ctx.cancelled():
            return self.cancelled()
        gate = _native(ctx, "computer_use_session", {"op": "gate", "action": action, "summary": args.get("action_summary") or action})
        if gate.get("status") == "error" or gate.get("error"):
            return gate if gate.get("status") else _error(gate.get("error"))
        if gate.get("user_control") and action in MUTATING:
            return _error("user has control")
        if gate.get("locked"):
            return _error("computer use is blocked while the session is locked")
        try:
            result = self._dispatch(ctx, action, args)
        except Exception as exc:
            return _error(str(exc))
        return _maybe_shot(ctx, args, result)

    def _dispatch(self, ctx, action, args):
        if action == "screenshot":
            return _capture(ctx, args, raise_window=args.get("raise_window"))
        if action == "snapshot":
            shot = _capture(ctx, args, raise_window=False)
            tree = []
            tree_error = ""
            try:
                win = None
                if args.get("address") or args.get("pid") or args.get("title") or args.get("class"):
                    win = cu_windows.resolve_window(_window_list(ctx), args)
                tree = atspi.snapshot_tree(
                    pid=(win or {}).get("pid") if win else args.get("pid"),
                    app_name=(win or {}).get("class") or args.get("class") or args.get("name"),
                    max_nodes=args.get("max_nodes"),
                    max_depth=args.get("max_depth"),
                )
                ctx.computer_use_nodes = tree
            except Exception as exc:
                tree_error = str(exc)
                ctx.computer_use_nodes = []
            out = dict(shot)
            out["accessibility_tree"] = tree
            out["accessibility_tree_raw_count"] = len(tree)
            if tree_error:
                out["accessibility_error"] = tree_error
            return out
        if action == "click":
            node = None
            err = ""
            if args.get("element_index") not in (None, "") or args.get("role") or args.get("name") or args.get("text"):
                node, err = atspi.resolve_node(ctx.computer_use_nodes, args)
                if err:
                    return _error(err)
            count = max(1, min(10, int(args.get("click_count") or 1)))
            button = str(args.get("button") or "left").lower()
            plain_left = button in ("left", "primary") and count == 1
            if node and plain_left:
                eq = atspi.click_equivalent(node)
                if eq is not None:
                    atspi.perform_action(node, eq)
                    return _ok({"implemented": "atspi", "element_index": node.get("index")})
            x, y, err, node = _resolve_point(ctx, args)
            if err:
                return _error(err)
            if x is None:
                return _error("could not resolve click coordinates")
            if args.get("address") or args.get("title") or args.get("class") or args.get("pid"):
                focused = _native(ctx, "use_computer", {"action": "focus", "warp": True, **{k: args.get(k) for k in ("address", "title", "class", "pid") if args.get(k) is not None}})
                if focused.get("status") == "error" or focused.get("error"):
                    return focused if focused.get("status") else _error(focused.get("error") or "could not focus target window")
                if focused.get("verified") is False:
                    return _error("could not focus target window")
                time.sleep(cu_input.FOCUS_SETTLE)
            if not cu_input.movecursor(x, y):
                return _error("movecursor failed")
            cu_input.click(button, count)
            return _ok({"implemented": "pointer", "x": x, "y": y})
        if action == "move":
            x, y, err, _node = _resolve_point(ctx, args)
            if err:
                return _error(err)
            if not cu_input.movecursor(x, y):
                return _error("movecursor failed")
            return _ok({"x": x, "y": y})
        if action == "scroll":
            x, y, err, _node = _resolve_point(ctx, args)
            if not err and x is not None:
                cu_input.movecursor(x, y)
            elif args.get("address") or args.get("title") or args.get("class") or args.get("pid"):
                focused = _native(ctx, "use_computer", {"action": "focus", "warp": True, **{k: args.get(k) for k in ("address", "title", "class", "pid") if args.get(k) is not None}})
                if focused.get("status") == "error" or focused.get("verified") is False:
                    return _error(focused.get("error") or "could not focus target window")
            cu_input.scroll(args.get("direction") or "down", args.get("pages") or 1)
            return _ok({"implemented": "wheel"})
        if action == "drag":
            start = coords.preview_to_logical(
                args.get("start_x") if args.get("start_x") is not None else args.get("x"),
                args.get("start_y") if args.get("start_y") is not None else args.get("y"),
                ctx.computer_use_last_shot or {},
            )
            end = coords.preview_to_logical(args.get("end_x"), args.get("end_y"), ctx.computer_use_last_shot or {})
            cu_input.drag(start, end, args.get("button") or "left")
            return _ok({"from": start, "to": end})
        if action == "type":
            if args.get("address") or args.get("title") or args.get("class") or args.get("pid"):
                focused = _native(ctx, "use_computer", {"action": "focus", **{k: args.get(k) for k in ("address", "title", "class", "pid") if args.get(k) is not None}})
                if focused.get("status") == "error" or focused.get("verified") is False:
                    return _error(focused.get("error") or "could not focus target window")
                time.sleep(cu_input.FOCUS_SETTLE)
            cu_input.type_text(args.get("text") or "")
            note = ""
            focused = atspi.focused_element()
            if focused and not focused.get("editable"):
                note = "WARNING: focused element is %s which is not editable" % (focused.get("role") or "unknown")
            return _ok({"implemented": "wtype", "focused": focused, "note": note})
        if action == "key":
            spec = args.get("key") or args.get("keys") or ""
            address = args.get("address") or ""
            if args.get("title") or args.get("class") or args.get("pid"):
                focused = cu_windows.resolve_window(_window_list(ctx), args)
                if focused:
                    address = focused.get("address") or address
            cu_input.press_key(spec, address=address)
            return _ok({"implemented": "key", "key": spec})
        if action in ("focus", "move_window", "resize_window", "cursor"):
            native = _native(ctx, "use_computer", args)
            if native.get("status") == "error":
                return native
            return _ok(native)
        if action == "wait":
            ms = max(0, min(WAIT_CAP_MS, int(args.get("ms") or 0)))
            time.sleep(ms / 1000.0)
            return _ok({"waited_ms": ms})
        if action == "perform_action":
            node, err = atspi.resolve_node(ctx.computer_use_nodes, args)
            if err or not node:
                return _error(err or "call snapshot first")
            atspi.perform_action(node, args.get("atspi_action") or args.get("perform"))
            return _ok({"implemented": "atspi"})
        if action == "set_value":
            node, err = atspi.resolve_node(ctx.computer_use_nodes, args)
            if err or not node:
                return _error(err or "call snapshot first")
            atspi.set_value(node, args.get("value"))
            return _ok({"implemented": "atspi"})
        return _error("unhandled action")

    def user_friendly_name_for(self, args):
        summary = ((args or {}).get("action_summary") or "").strip()
        action = ((args or {}).get("action") or "").strip()
        label = summary or action or "computer"
        return labels(
            "Using computer: %s" % label,
            "Used computer: %s" % label,
            ask="Use computer: %s" % label,
        )
