"""Window targeting and /proc terminal enrichment."""

from __future__ import annotations

import os
from pathlib import Path

TERMINAL_HINTS = (
    "kitty",
    "alacritty",
    "ghostty",
    "foot",
    "wezterm",
    "konsole",
    "gnome-terminal",
    "tilix",
    "terminator",
    "xfce4-terminal",
    "ptyxis",
    "rio",
    "contour",
)


def _norm(value):
    return " ".join(str(value or "").lower().split())


def enrich_terminal(window):
    pid = window.get("pid")
    if not pid:
        return window
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return window
    ident = _norm(window.get("class") or window.get("class_name") or "")
    title = _norm(window.get("title") or "")
    if not any(hint in ident or hint in title for hint in TERMINAL_HINTS):
        return window
    proc = Path("/proc") / str(pid)
    if not proc.is_dir():
        return window
    tty = ""
    try:
        fd0 = os.readlink(str(proc / "fd" / "0"))
        if "pts" in fd0:
            tty = fd0
    except OSError:
        pass
    cmdline = ""
    cwd = ""
    try:
        cmdline = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except OSError:
        pass
    try:
        cwd = os.readlink(str(proc / "cwd"))
    except OSError:
        pass
    window["terminal"] = {
        "tty": tty,
        "pid": pid,
        "command": cmdline,
        "cwd": cwd,
    }
    return window


def resolve_window(windows, target):
    windows = list(windows or [])
    target = target or {}
    address = str(target.get("address") or target.get("window_id") or "").strip()
    if address:
        for win in windows:
            if addresses_equal(win.get("address"), address):
                return win
        return None
    tty = str(target.get("tty") or "").strip()
    term_pid = target.get("terminal_pid")
    term_cmd = _norm(target.get("terminal_command") or "")
    term_cwd = str(target.get("terminal_cwd") or "").strip()
    if tty or term_pid or term_cmd or term_cwd:
        matches = []
        for win in windows:
            term = win.get("terminal") or {}
            if tty:
                raw = str(term.get("tty") or "")
                if tty not in (raw, os.path.basename(raw)) and not raw.endswith(tty):
                    continue
            if term_pid not in (None, ""):
                try:
                    if int(term.get("pid") or 0) != int(term_pid) and int(win.get("pid") or 0) != int(term_pid):
                        continue
                except (TypeError, ValueError):
                    continue
            if term_cmd and term_cmd not in _norm(term.get("command") or ""):
                continue
            if term_cwd and not str(term.get("cwd") or "").endswith(term_cwd):
                continue
            matches.append(win)
        if len(matches) == 1:
            return matches[0]
        return None
    pid = target.get("pid")
    if pid not in (None, ""):
        hits = [w for w in windows if str(w.get("pid") or "") == str(pid)]
        if len(hits) == 1:
            return hits[0]
        return None
    class_name = _norm(target.get("class") or target.get("app_id") or target.get("wm_class") or "")
    if class_name:
        for win in windows:
            ident = _norm(win.get("class") or win.get("class_name") or "")
            if ident == class_name:
                return win
    title = _norm(target.get("title") or target.get("window_title") or "")
    if title:
        for win in windows:
            if title in _norm(win.get("title") or ""):
                return win
    return None


def canonical_address(value):
    """Hyprland window address: strip address:, collapse 0x0x, lowercase."""
    text = str(value or "").strip()
    if text.lower().startswith("address:"):
        text = text[8:].strip()
    lowered = text.lower()
    while lowered.startswith("0x0x"):
        text = "0x" + text[4:]
        lowered = text.lower()
    if text and not lowered.startswith("0x"):
        hexish = all(ch in "0123456789abcdef" for ch in lowered)
        if hexish:
            text = "0x" + text
            lowered = text.lower()
    return lowered


def normalize_address(value):
    return canonical_address(value)


def addresses_equal(left, right):
    want = canonical_address(left)
    got = canonical_address(right)
    return bool(want) and want == got


def workspace_id(value):
    if value in (None, "", False):
        return None
    if isinstance(value, dict):
        return workspace_id(value.get("id") if value.get("id") not in (None, "") else value.get("name"))
    try:
        number = int(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None
    return number if number else None


def active_matches_target(target, active, monitor_active_workspace=None):
    """Address + optional workspace match. Not sufficient for Hyprland handoff.

    Cache `is_focused` plus the window's own workspace id can agree while that
    workspace is still inactive (or a layer-shell Exclusive grab holds keys).
    Use live_focus_confirmed() with hyprctl activewindow + monitors.
    """
    if not target or not active:
        return False
    if not addresses_equal(target.get("address") or target.get("window_id"), active.get("address") or active.get("window_id")):
        return False
    if active.get("focused") is False or active.get("is_focused") is False:
        return False
    want_ws = workspace_id(monitor_active_workspace)
    if want_ws is None:
        want_ws = workspace_id(active.get("workspace"))
    target_ws = workspace_id(target.get("workspace"))
    if want_ws is not None and target_ws is not None and want_ws != target_ws:
        return False
    return True


def _monitor_active_workspace(monitors, monitor_id):
    for mon in monitors or []:
        mid = mon.get("id")
        name = mon.get("name")
        if monitor_id not in (None, "") and str(mid) != str(monitor_id) and name != monitor_id:
            continue
        aw = mon.get("activeWorkspace") or mon.get("active_workspace") or {}
        if isinstance(aw, dict):
            ident = aw.get("id") if aw.get("id") not in (None, "") else aw.get("name")
            return workspace_id(ident), str(aw.get("name") or aw.get("id") or "")
        return workspace_id(aw), str(aw or "")
    return None, ""


def live_focus_confirmed(target, activewindow, monitors):
    """True only from live hyprctl activewindow + monitors — never cache is_focused.

    Empty/missing activewindow fails. Matching address is required. The target's
    workspace must be the active workspace on its monitor.
    """
    if not target or not isinstance(activewindow, dict):
        return False
    addr = activewindow.get("address") or activewindow.get("window_id")
    if not addr:
        return False
    if not addresses_equal(target.get("address") or target.get("window_id"), addr):
        return False
    if not isinstance(monitors, (list, tuple)):
        return False
    target_ws = workspace_id(target.get("workspace"))
    if target_ws is None:
        target_ws = workspace_id(activewindow.get("workspace"))
    mon_id = target.get("monitor")
    if mon_id in (None, ""):
        mon_id = activewindow.get("monitor")
    shown_ws, shown_name = _monitor_active_workspace(monitors, mon_id)
    if shown_ws is None and not shown_name:
        return False
    if target_ws is not None and shown_ws is not None and target_ws != shown_ws:
        return False
    target_name = ""
    ws = target.get("workspace")
    if isinstance(ws, dict):
        target_name = str(ws.get("name") or "")
    elif ws not in (None, ""):
        target_name = str(ws)
    if target_ws is None and target_name and shown_name and target_name != shown_name:
        return False
    return True


def handoff_steps(window, monitors=None, focused_monitor_id=None, warp=False):
    """Bounded Hyprland focus recipe: monitor, workspace, focuswindow, raise, optional warp."""
    window = window or {}
    steps = []
    mon_id = window.get("monitor")
    if mon_id not in (None, "") and focused_monitor_id not in (None, "") and str(mon_id) != str(focused_monitor_id):
        steps.append(("focusmonitor", str(mon_id)))
    ws = window.get("workspace") or {}
    ws_name = str(ws.get("name") or "") if isinstance(ws, dict) else str(ws or "")
    ws_ident = workspace_id(ws)
    mon_ws, mon_ws_name = _monitor_active_workspace(monitors, mon_id)
    if ws_name.startswith("special"):
        special = ws_name.split(":", 1)[-1] if ":" in ws_name else ws_name
        if not str(mon_ws_name).startswith("special"):
            steps.append(("togglespecialworkspace", special))
    elif ws_ident is not None and (mon_ws is None or ws_ident != mon_ws):
        steps.append(("workspace", str(ws_ident)))
    elif ws_name and mon_ws_name and ws_name != mon_ws_name and ws_ident is None:
        steps.append(("workspace", ws_name))
    addr = canonical_address(window.get("address"))
    if addr:
        steps.append(("focuswindow", "address:" + addr))
    steps.append(("bringactivetotop", ""))
    if warp:
        at = window.get("at") or [0, 0]
        size = window.get("size") or [0, 0]
        try:
            cx = int(round(float(at[0]) + float(size[0]) / 2.0))
            cy = int(round(float(at[1]) + float(size[1]) / 2.0))
        except (TypeError, ValueError, IndexError):
            cx = cy = None
        if cx is not None:
            steps.append(("movecursor", "%s %s" % (cx, cy)))
    return steps


FOCUS_UNCONFIRMED = "could not confirm keyboard focus"


def focus_unconfirmed_message(target=None, active=None):
    target = target or {}
    want = target.get("title") or target.get("class") or target.get("class_name") or "target window"
    addr = normalize_address(target.get("address") or target.get("window_id")) or "?"
    msg = "could not confirm keyboard focus on %s (address %s)" % (want, addr)
    if active:
        got = active.get("title") or active.get("class") or active.get("class_name") or "unknown"
        got_addr = normalize_address(active.get("address") or active.get("window_id")) or "?"
        msg += "; activewindow is %s (address %s)" % (got, got_addr)
    else:
        msg += "; activewindow did not match"
    msg += ". Do not retry with hyprctl; focus handoff failed."
    return msg
