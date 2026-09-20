"""Native computer-use tools. Policy default is Never."""

from __future__ import annotations

import re
import time

from .registry import Tool
from .friendly import labels
from .native import native_request
from ..execution_profile import ALWAYS_ALLOW, NEVER
from ..computer_use import atspi, coords, doctor, input as cu_input, screenshot as cu_shot, windows as cu_windows
from ..models import (
    apply_computer_use_model,
    model_supports_vision,
    restore_chat_model,
    vision_unsupported_message,
)

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

OBSERVE_AFTER = {
    "click",
    "scroll",
    "drag",
    "move",
    "type",
    "key",
    "perform_action",
    "set_value",
    "wait",
    "focus",
}

WAIT_CAP_MS = 5000
VISION_UNSUPPORTED = "vision_unsupported"
PIXEL_ACTIONS = {"screenshot", "click", "move", "drag", "scroll", "cursor"}

# Exact control labels that commit money, mail, or account destruction.
_CRITICAL_LABEL = re.compile(
    r"(?ix)^\s*("
    r"send(?:\s+(?:now|email|e-?mail|message|it))?"
    r"|pay(?:\s+now)?"
    r"|buy(?:\s+now)?"
    r"|purchase"
    r"|checkout"
    r"|place\s+(?:an?\s+)?order"
    r"|order\s+now"
    r"|submit\s+(?:order|payment|purchase)"
    r"|confirm\s+(?:purchase|payment|order)"
    r"|transfer(?:\s+money)?"
    r"|donate"
    r"|subscribe(?:\s+now)?"
    r"|delete\s+account"
    r"|permanently\s+delete"
    r")\s*$"
)

# Looser match for action_summary / typed intent.
_CRITICAL_SUMMARY = re.compile(
    r"(?ix)\b("
    r"pay(?:ment|pal)?"
    r"|purchase"
    r"|checkout"
    r"|place\s+(?:an?\s+)?order"
    r"|send(?:ing)?\s+(?:(?:the|an?)\s+)?(?:e-?mail|mail|message)"
    r"|buy\s+now"
    r"|complete\s+(?:the\s+)?purchase"
    r"|transfer\s+money"
    r"|delete\s+(?:the\s+)?account"
    r")\b"
)

_SEND_CHORD = re.compile(r"(?i)(ctrl|control|cmd|command|super|meta)\s*\+\s*(enter|return)")


def _truthy(value):
    return value is True or value == 1 or str(value).strip().lower() in ("true", "1", "yes")


def _node_label(ctx, args):
    idx = (args or {}).get("element_index")
    if idx is None or idx == "":
        return ""
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return ""
    for node in getattr(ctx, "computer_use_nodes", None) or []:
        if node.get("index") == idx:
            return str(node.get("name") or "")
    return ""


def _target_texts(ctx, args):
    args = args or {}
    texts = []
    for key in ("action_summary", "name", "text", "atspi_action", "perform", "value"):
        val = args.get(key)
        if val:
            texts.append(str(val))
    label = _node_label(ctx, args)
    if label:
        texts.append(label)
    return texts


def action_is_critical(ctx, args):
    """True for irreversible desktop actions (pay, send mail, purchase, …)."""
    args = args or {}
    if _truthy(args.get("critical") or args.get("requires_confirmation")):
        return True
    action = str(args.get("action") or "").strip()
    if action in ("screenshot", "snapshot", "cursor", "wait", "focus", "move", "scroll", "move_window", "resize_window", "type"):
        return False
    spec = str(args.get("key") or args.get("keys") or "")
    if action == "key" and _SEND_CHORD.search(spec):
        return True
    texts = _target_texts(ctx, args)
    for text in texts:
        stripped = text.strip()
        if _CRITICAL_LABEL.match(stripped):
            return True
        if _CRITICAL_SUMMARY.search(stripped):
            return True
    return False


def _leave_computer_use(ctx):
    if getattr(ctx, "computer_use_approved", False):
        try:
            _native(ctx, "computer_use_session", {"op": "end"})
        except Exception:
            pass
    ctx.computer_use_approved = False
    ctx.computer_use_nodes = []
    ctx.computer_use_last_shot = None
    ctx.computer_use_focus_address = ""
    restore_chat_model(ctx)


def _require_vision(ctx):
    spec = apply_computer_use_model(ctx)
    if model_supports_vision(spec):
        return None
    _leave_computer_use(ctx)
    return _error(vision_unsupported_message(spec), extra={"code": VISION_UNSUPPORTED})


def _needs_screenshot(action, args):
    if action == "screenshot" or (args or {}).get("screenshot") is True:
        return True
    if str((args or {}).get("observe") or "") == "screenshot":
        return True
    if action in PIXEL_ACTIONS and (
        (args or {}).get("x") is not None or (args or {}).get("y") is not None
    ):
        return True
    return False


def _begin_session(ctx, summary):
    blocked = _require_vision(ctx)
    if blocked:
        return blocked
    native = _native(
        ctx,
        "computer_use_session",
        {"op": "begin", "task_summary": summary or ""},
    )
    if native.get("status") == "error" or native.get("error"):
        return native if native.get("status") else _error(native.get("error"))
    if native.get("locked"):
        return _error("computer use is blocked while the session is locked")
    ctx.computer_use_approved = True
    ctx.computer_use_nodes = []
    return native


def _error(message, extra=None):
    out = {"status": "error", "error": message}
    if extra:
        out.update(extra)
    return out


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


def _observe_mode(args):
    raw = args.get("observe")
    if raw is None:
        return "tree"
    text = str(raw).strip().lower()
    if text in ("none", "false", "0", "off"):
        return "none"
    if text in ("screenshot", "image", "pixels", "shot"):
        return "screenshot"
    return "tree"


def _maybe_shot(ctx, args, result):
    if not isinstance(result, dict) or result.get("status") == "error":
        return result
    if args.get("screenshot") is not True:
        return result
    action = args.get("action")
    if action in ("screenshot", "snapshot", "cursor", "wait"):
        return result
    shot = _capture(ctx, args, raise_window=False)
    if shot.get("status") != "error":
        result["screenshot"] = {k: v for k, v in shot.items() if k != "image_base64"}
        if shot.get("image_base64"):
            result["image_base64"] = shot["image_base64"]
            result["mime_type"] = shot.get("mime_type") or "image/jpeg"
            result["path"] = shot.get("path")
    return result


def _capture_args(ctx, args):
    address = args.get("address") or args.get("window_id") or getattr(ctx, "computer_use_focus_address", "") or ""
    return {
        "action": "screenshot",
        "target": args.get("target"),
        "monitor": args.get("monitor"),
        "address": address,
        "full_screen": bool(args.get("full_screen")),
        "raise_window": True if args.get("raise_window") is None else bool(args.get("raise_window")),
        "include_cursor": args.get("include_cursor", True),
        "geometry": args.get("geometry"),
    }


def _capture(ctx, args, raise_window=None):
    payload = _capture_args(ctx, args)
    if raise_window is not None:
        payload["raise_window"] = bool(raise_window)
    native = _native(ctx, "use_computer", payload)
    if native.get("status") == "error" or native.get("error"):
        return native if native.get("status") else _error(native.get("error") or "screenshot failed")
    if native.get("verified") is False:
        return _error(
            native.get("error")
            or cu_windows.focus_unconfirmed_message(
                {"address": payload.get("address")}, native.get("focused_window")
            )
        )
    path = native.get("path")
    if not path:
        return _error("screenshot produced no file")
    try:
        prepared = cu_shot.prepare_payload(
            path,
            max_width=args.get("max_width") or 1280,
            max_height=args.get("max_height") or 1280,
            max_bytes=args.get("max_bytes"),
            scale=args.get("scale"),
            fmt=args.get("format") or "jpeg",
            quality=args.get("quality") if args.get("quality") is not None else 70,
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
            "address": native.get("address") or payload.get("address") or "",
            "verified": native.get("verified"),
            "source": "grim",
        }
    )
    if native.get("address"):
        _remember_focus(ctx, native)
    ctx.computer_use_last_shot = {
        k: prepared[k]
        for k in (
            "scale",
            "width",
            "height",
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


PIXEL_SHOT_NEEDED = "screenshot first; x/y are pixels of that image (width x height)"


def _preview_xy(args, start=False):
    if start:
        x = args.get("start_x") if args.get("start_x") is not None else args.get("x")
        y = args.get("start_y") if args.get("start_y") is not None else args.get("y")
        return x, y
    return args.get("x"), args.get("y")


def _resolve_point(ctx, args, start=False):
    meta = ctx.computer_use_last_shot or {}
    x, y = _preview_xy(args, start=start)
    if x is None or y is None:
        node, err = atspi.resolve_node(ctx.computer_use_nodes, args)
        if err:
            return None, None, err, node, None
        return None, None, PIXEL_SHOT_NEEDED, node, None
    if args.get("relative") and not meta:
        return None, None, "relative coordinates need a prior screenshot of the target window", None, None
    if not meta:
        return None, None, PIXEL_SHOT_NEEDED, None, None
    lx, ly = coords.preview_to_logical(x, y, meta)
    return lx, ly, "", None, (x, y)


def _pointer_payload(preview, logical, extra=None):
    px, py = preview if preview else (None, None)
    out = {
        "x": px,
        "y": py,
        "logical_x": logical[0] if logical else None,
        "logical_y": logical[1] if logical else None,
    }
    if extra:
        out.update(extra)
    return out


def _with_inject(ctx, fn):
    _native(ctx, "computer_use_session", {"op": "inject_begin"})
    try:
        return fn()
    finally:
        _native(ctx, "computer_use_session", {"op": "inject_end"})


def _slim_windows(windows):
    out = []
    for win in windows or []:
        out.append(
            {
                "address": win.get("address") or "",
                "title": win.get("title") or "",
                "class": win.get("class") or win.get("class_name") or "",
                "pid": win.get("pid") or 0,
                "focused": bool(win.get("focused") or win.get("is_focused")),
                "at": win.get("at") or [],
                "size": win.get("size") or [],
                "workspace": win.get("workspace") or {},
            }
        )
    return out


def _remember_focus(ctx, win):
    address = (win or {}).get("address") or ""
    if address:
        ctx.computer_use_focus_address = address


def _target_selectors(ctx, args, include_remembered=True):
    args = args or {}
    sel = {}
    for key in ("address", "title", "class", "pid"):
        val = args.get(key)
        if val not in (None, ""):
            sel[key] = val
    if "address" not in sel:
        wid = args.get("window_id")
        if wid not in (None, ""):
            sel["address"] = wid
    if not sel and include_remembered:
        remembered = getattr(ctx, "computer_use_focus_address", "") or ""
        if remembered:
            sel["address"] = remembered
    return sel


def _rejected_focus(native, target=None):
    if not isinstance(native, dict):
        return _error(cu_windows.focus_unconfirmed_message(target))
    if native.get("status") == "error" or native.get("error"):
        err = native.get("error") or cu_windows.focus_unconfirmed_message(target, native.get("focused_window"))
        return native if native.get("status") == "error" else _error(err)
    if native.get("verified") is not True:
        return _error(
            native.get("error") or cu_windows.focus_unconfirmed_message(target, native.get("focused_window"))
        )
    return None


def _ensure_focus(ctx, args, warp=False, include_remembered=True):
    """One native focus-by-address. QML verifies and retries once; we fail closed."""
    sel = _target_selectors(ctx, args, include_remembered=include_remembered)
    if not sel:
        return None
    payload = {"action": "focus", **sel}
    if warp:
        payload["warp"] = True
    native = _native(ctx, "use_computer", payload)
    rejected = _rejected_focus(native, sel)
    if rejected:
        return rejected
    _remember_focus(ctx, native)
    time.sleep(cu_input.FOCUS_SETTLE)
    return native


def _a11y_followup(ctx, node=None):
    payload = {}
    if node:
        payload["element"] = atspi.slim_node(node)
        payload["element_index"] = node.get("index")
    focused = atspi.focused_from_nodes(getattr(ctx, "computer_use_nodes", None) or [])
    if focused:
        payload["focused"] = focused
    return payload


def _snapshot_state(ctx, args):
    windows_raw = _window_list(ctx)
    windows = _slim_windows(windows_raw)
    win = None
    if args.get("address") or args.get("pid") or args.get("title") or args.get("class"):
        win = cu_windows.resolve_window(windows_raw, args)
    elif windows_raw:
        win = next((w for w in windows_raw if w.get("focused") or w.get("is_focused")), None)
    if win:
        _remember_focus(ctx, win)
    tree = []
    tree_error = ""
    try:
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
    focused = atspi.focused_from_nodes(tree)
    usable = atspi.tree_usable(tree)
    out = {
        "windows": windows,
        "focused_window": _slim_windows([win])[0] if win else next((w for w in windows if w.get("focused")), None),
        "accessibility_tree": atspi.public_tree(tree),
        "accessibility_tree_raw_count": len(tree),
        "tree_usable": usable,
        "focused": focused,
    }
    if tree_error:
        out["accessibility_error"] = tree_error
    if not usable:
        out["accessibility_hint"] = atspi.A11Y_HINT
    return out


def _attach_shot_fields(dst, shot):
    if not isinstance(shot, dict) or shot.get("status") == "error":
        dst["screenshot_error"] = (shot or {}).get("error") or "screenshot failed"
        return dst
    for key, value in shot.items():
        if key == "status":
            continue
        dst[key] = value
    return dst


def _attach_observe(ctx, args, result, force_shot=False):
    if not isinstance(result, dict) or result.get("status") == "error":
        return result
    mode = _observe_mode(args)
    if mode == "none" and not force_shot and args.get("screenshot") is not True:
        return result
    state = _snapshot_state(ctx, args)
    result.update(state)
    want_shot = force_shot or args.get("screenshot") is True or mode == "screenshot" or state.get("tree_usable") is False
    if want_shot:
        shot = _capture(ctx, args, raise_window=False)
        _attach_shot_fields(result, shot)
    return result


def _pixel_needed(ctx, args):
    extra = {"next": {"action": "screenshot"}}
    shot = _capture(ctx, args, raise_window=False)
    if shot.get("status") != "error" and shot.get("image_base64"):
        extra["next"] = {"action": "click", "x": args.get("x"), "y": args.get("y")}
        extra["note"] = "captured grim JPEG; retry click using this image's width x height"
        extra.update({k: v for k, v in shot.items() if k != "status"})
    return _error(PIXEL_SHOT_NEEDED, extra)


def _steps(args):
    args = args or {}
    batch = args.get("actions") if isinstance(args.get("actions"), list) else None
    steps = []
    if args.get("action"):
        head = dict(args)
        head.pop("actions", None)
        steps.append(head)
    if batch:
        for item in batch:
            if isinstance(item, dict):
                steps.append(item)
    return steps


class RequestComputerUseTool(Tool):
    name = "request_computer_use"
    user_friendly_name = "Request computer use"
    schema = {
        "description": (
            "Request permission to observe and control the desktop (screenshots, clicks, typing). "
            "Call this before use_computer. Returns a compact doctor report (can_click/can_type/tree)."
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
        blocked = _require_vision(ctx)
        if blocked:
            return blocked
        native = _begin_session(ctx, (args or {}).get("task_summary") or "")
        if native.get("status") == "error" or native.get("error"):
            return native
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
            "Control the local desktop. Prefer action=snapshot (accessibility tree + windows, no pixels). "
            "Click with element_index. action=screenshot is grim JPEG for the agent — never the human overlay. "
            "Pixel x/y are in the last attached grim image (width x height). "
            "After click/type/key/scroll/drag the harness returns a fresh tree (JPEG only if the tree is empty). "
            "actions[] is an ordered batch and is honored even when action is also set (action runs first). "
            "Set observe=none to skip the harness recapture. Hyprland-only cursor/shortcuts; Niri/Mango cannot aim."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(ACTIONS),
                    "description": (
                        "snapshot=tree; screenshot=grim JPEG; click/type/key/scroll/drag/move; "
                        "focus/move_window/resize_window; perform_action/set_value; wait; cursor"
                    ),
                },
                "actions": {
                    "type": "array",
                    "description": "Ordered batch. Runs after a top-level action if both are set. Stops on first error. Observe once at the end.",
                    "items": {"type": "object"},
                },
                "observe": {
                    "type": "string",
                    "enum": ["tree", "screenshot", "none"],
                    "description": "Harness recapture after mutate. Default tree; screenshot if tree_usable is false.",
                },
                "action_summary": {"type": "string"},
                "critical": {
                    "type": "boolean",
                    "description": (
                        "Set true before payments, sending email or messages, purchases, "
                        "or other irreversible actions so the user can confirm."
                    ),
                },
                "x": {
                    "type": "number",
                    "description": "Pixel X in the last attached grim screenshot (width x height of that image)",
                },
                "y": {
                    "type": "number",
                    "description": "Pixel Y in the last attached grim screenshot (width x height of that image)",
                },
                "start_x": {"type": "number"},
                "start_y": {"type": "number"},
                "end_x": {"type": "number"},
                "end_y": {"type": "number"},
                "button": {"type": "string"},
                "click_count": {"type": "integer"},
                "direction": {"type": "string"},
                "pages": {"type": "number"},
                "text": {"type": "string", "description": "Text to type (action=type)"},
                "key": {"type": "string", "description": "Key or chord (ctrl+c). keys is an alias."},
                "keys": {"type": "string", "description": "Alias of key"},
                "ms": {"type": "integer", "description": "Wait milliseconds (capped at 5000)"},
                "element_index": {"type": "integer", "description": "Index from the last snapshot tree"},
                "role": {"type": "string"},
                "name": {"type": "string"},
                "states": {"type": "array", "items": {"type": "string"}},
                "value": {"type": "string"},
                "address": {"type": "string", "description": "Window address string from snapshot/get_windows"},
                "pid": {"type": "integer"},
                "title": {"type": "string"},
                "class": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "screenshot": {"type": "boolean", "description": "Force a grim JPEG on this call"},
                "full_screen": {"type": "boolean"},
                "geometry": {"type": "string", "description": "Optional grim crop WxH+X+Y; does not change click origin unless this is the last_shot"},
            },
            "required": ["action"],
        },
    }

    def should_autoexecute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return "deny"
        from ..jev_judgments import require_critical_review

        regex_critical = action_is_critical(ctx, args)
        if require_critical_review(ctx, args, regex_critical):
            return "ask"
        if ctx.computer_use_approved or ctx.profile.computer_use == ALWAYS_ALLOW or ctx.autoexecute_any_action:
            return True
        return "ask"

    def execute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return _error("computer use is disabled")
        blocked = _require_vision(ctx)
        if blocked:
            return blocked
        args = args or {}
        if not ctx.computer_use_approved:
            native = _begin_session(
                ctx,
                args.get("action_summary") or args.get("task_summary") or args.get("action") or "",
            )
            if native.get("status") == "error" or native.get("error"):
                return native
        steps = _steps(args)
        if not steps:
            return _error("unknown action: (empty)")
        results = []
        last = None
        for i, step in enumerate(steps):
            last = self._one(ctx, step, observe=(i == len(steps) - 1))
            results.append(last)
            if last.get("status") == "error":
                if len(steps) == 1:
                    return last
                extra = {"results": results}
                for key in ("next", "image_base64", "mime_type", "width", "height", "note"):
                    if key in last:
                        extra[key] = last[key]
                return _error(last.get("error") or "action failed", extra)
        if len(steps) == 1:
            return last
        out = _ok({"results": results})
        for key in (
            "windows",
            "accessibility_tree",
            "tree_usable",
            "focused",
            "focused_window",
            "image_base64",
            "mime_type",
            "width",
            "height",
            "path",
        ):
            if last and key in last:
                out[key] = last[key]
        return out

    def _one(self, ctx, args, observe=True):
        action = str(args.get("action") or "").strip()
        if action not in ACTIONS:
            return _error("unknown action: %s" % (action or "(empty)"))
        if ctx.cancelled():
            return self.cancelled()
        if _needs_screenshot(action, args):
            blocked = _require_vision(ctx)
            if blocked:
                return blocked
        gate = _native(ctx, "computer_use_session", {"op": "gate", "action": action, "summary": args.get("action_summary") or action})
        if gate.get("status") == "error" or gate.get("error"):
            return gate if gate.get("status") else _error(gate.get("error"))
        if (gate.get("user_control") or gate.get("composer_focused") or gate.get("steer_open")) and action in MUTATING:
            return _error("user has control" if gate.get("user_control") else "user is steering")
        if gate.get("locked"):
            return _error("computer use is blocked while the session is locked")
        try:
            result = self._dispatch(ctx, action, args)
        except Exception as exc:
            return _error(str(exc))
        if not observe:
            return _maybe_shot(ctx, args, result)
        if action in ("screenshot", "snapshot", "cursor"):
            return result
        if action in OBSERVE_AFTER:
            return _attach_observe(ctx, args, result)
        return _maybe_shot(ctx, args, result)

    def _dispatch(self, ctx, action, args):
        if action == "screenshot":
            return _capture(ctx, args, raise_window=args.get("raise_window"))
        if action == "snapshot":
            focused = _ensure_focus(ctx, args, include_remembered=False)
            if focused and focused.get("status") == "error":
                return focused
            out = _ok(_snapshot_state(ctx, args))
            if args.get("screenshot") is True or out.get("tree_usable") is False:
                shot = _capture(ctx, args, raise_window=False)
                _attach_shot_fields(out, shot)
            return out
        if action == "click":
            focused = _ensure_focus(ctx, args, warp=True)
            if focused and focused.get("status") == "error":
                return focused
            node = None
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
                    follow = _a11y_followup(ctx, node)
                    follow.update({"implemented": "atspi", "element_index": node.get("index")})
                    return _ok(follow)
                center = atspi.bounds_center(node)
                if center:
                    cu_input.movecursor(center[0], center[1])
                    cu_input.click(button, count)
                    follow = _a11y_followup(ctx, node)
                    follow.update(
                        {
                            "implemented": "bounds",
                            "element_index": node.get("index"),
                            "logical_x": int(round(center[0])),
                            "logical_y": int(round(center[1])),
                        }
                    )
                    return _ok(follow)
            x, y, err, node, preview = _resolve_point(ctx, args)
            if err == PIXEL_SHOT_NEEDED:
                return _pixel_needed(ctx, args)
            if err:
                return _error(err)
            if x is None:
                return _error("could not resolve click coordinates")
            cu_input.movecursor(x, y)
            cu_input.click(button, count)
            return _ok(_pointer_payload(preview, (x, y), {"implemented": "pointer"}))
        if action == "move":
            x, y, err, _node, preview = _resolve_point(ctx, args)
            if err == PIXEL_SHOT_NEEDED:
                return _pixel_needed(ctx, args)
            if err:
                return _error(err)
            cu_input.movecursor(x, y)
            return _ok(_pointer_payload(preview, (x, y)))
        if action == "scroll":
            focused = _ensure_focus(ctx, args, warp=True)
            if focused and focused.get("status") == "error":
                return focused
            x, y, err, _node, preview = _resolve_point(ctx, args)
            if not err and x is not None:
                try:
                    cu_input.movecursor(x, y)
                except RuntimeError:
                    pass
            elif err == PIXEL_SHOT_NEEDED and (args.get("x") is not None or args.get("y") is not None):
                pass
            cu_input.scroll(args.get("direction") or "down", args.get("pages") or 1)
            return _ok({"implemented": "wheel"})
        if action == "drag":
            sx, sy, err, _node, start_preview = _resolve_point(ctx, args, start=True)
            if err == PIXEL_SHOT_NEEDED:
                return _pixel_needed(ctx, args)
            if err:
                return _error(err)
            end_args = dict(args)
            end_args["x"] = args.get("end_x")
            end_args["y"] = args.get("end_y")
            ex, ey, err, _node2, end_preview = _resolve_point(ctx, end_args)
            if err == PIXEL_SHOT_NEEDED:
                return _pixel_needed(ctx, end_args)
            if err:
                return _error(err)
            cu_input.drag((sx, sy), (ex, ey), args.get("button") or "left")
            return _ok(
                {
                    "from": {"x": (start_preview or [None, None])[0], "y": (start_preview or [None, None])[1]},
                    "to": {"x": (end_preview or [None, None])[0], "y": (end_preview or [None, None])[1]},
                    "logical_from": [sx, sy],
                    "logical_to": [ex, ey],
                }
            )
        if action == "type":
            focused = _ensure_focus(ctx, args)
            if focused and focused.get("status") == "error":
                return focused
            _with_inject(ctx, lambda: cu_input.type_text(args.get("text") or ""))
            focused = atspi.focused_from_nodes(getattr(ctx, "computer_use_nodes", None) or [])
            note = ""
            if focused and not focused.get("editable"):
                note = "WARNING: focused element is %s which is not editable" % (focused.get("role") or "unknown")
            return _ok({"implemented": "wtype", "focused": focused, "note": note})
        if action == "key":
            focused = _ensure_focus(ctx, args)
            if focused and focused.get("status") == "error":
                return focused
            spec = args.get("key") or args.get("keys") or ""
            address = args.get("address") or getattr(ctx, "computer_use_focus_address", "") or ""
            if not address and (args.get("title") or args.get("class") or args.get("pid")):
                resolved = cu_windows.resolve_window(_window_list(ctx), args)
                if resolved:
                    address = resolved.get("address") or address
            _with_inject(ctx, lambda: cu_input.press_key(spec, address=address))
            return _ok({"implemented": "key", "key": spec})
        if action in ("focus", "move_window", "resize_window", "cursor"):
            native = _native(ctx, "use_computer", dict(args, action=action))
            if native.get("status") == "error":
                return native
            if action == "focus":
                rejected = _rejected_focus(native, args)
                if rejected:
                    return rejected
                _remember_focus(ctx, native)
            return _ok(native)
        if action == "wait":
            ms = max(0, min(WAIT_CAP_MS, int(args.get("ms") or 0)))
            _native(ctx, "computer_use_session", {"op": "wait_begin", "ms": ms})
            try:
                time.sleep(ms / 1000.0)
            finally:
                _native(ctx, "computer_use_session", {"op": "wait_end"})
            return _ok({"waited_ms": ms})
        if action == "perform_action":
            node, err = atspi.resolve_node(ctx.computer_use_nodes, args)
            if err or not node:
                return _error(err or "call snapshot first")
            atspi.perform_action(node, args.get("atspi_action") or args.get("perform"))
            follow = _a11y_followup(ctx, node)
            follow["implemented"] = "atspi"
            return _ok(follow)
        if action == "set_value":
            node, err = atspi.resolve_node(ctx.computer_use_nodes, args)
            if err or not node:
                return _error(err or "call snapshot first")
            atspi.set_value(node, args.get("value"))
            follow = _a11y_followup(ctx, node)
            follow["implemented"] = "atspi"
            return _ok(follow)
        return _error("unhandled action")

    def user_friendly_name_for(self, args):
        summary = ((args or {}).get("action_summary") or "").strip()
        action = ((args or {}).get("action") or "").strip()
        label = summary or action or "computer"
        ask = "Confirm: %s" % label if action_is_critical(None, args) else "Use computer: %s" % label
        return labels(
            "Using computer: %s" % label,
            "Used computer: %s" % label,
            ask=ask,
        )
