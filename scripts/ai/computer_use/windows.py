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
            if str(win.get("address") or "") == address:
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
