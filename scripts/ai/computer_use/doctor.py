"""Readiness probes for native computer use."""

from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path


def _which(name):
    return shutil.which(name) or ""


def ydotool_socket_path():
    env = os.environ.get("YDOTOOL_SOCKET")
    if env:
        return env
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return str(Path(runtime) / ".ydotool_socket")


def ydotool_socket_ok():
    path = ydotool_socket_path()
    if not os.path.exists(path):
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.settimeout(0.2)
        sock.connect(path)
        return True
    except OSError:
        return False
    finally:
        sock.close()


def uinput_writable():
    path = "/dev/uinput"
    return os.path.exists(path) and os.access(path, os.W_OK)


def probe_binaries():
    return {
        "grim": bool(_which("grim")),
        "wtype": bool(_which("wtype")),
        "ydotool": bool(_which("ydotool")),
        "ydotoold": bool(_which("ydotoold")),
        "hyprctl": bool(_which("hyprctl")),
        "axctl": bool(_which("axctl")),
        "convert": bool(_which("convert") or _which("magick")),
        "identify": bool(_which("identify") or _which("magick")),
    }


def doctor_report(native=None, atspi_ok=None):
    bins = probe_binaries()
    native = native or {}
    ydo_sock = ydotool_socket_ok()
    report = {
        "grim": bins["grim"],
        "wtype": bins["wtype"],
        "ydotool": bins["ydotool"],
        "ydotool_socket": ydo_sock,
        "uinput": uinput_writable(),
        "sendshortcut": bins["hyprctl"],
        "movecursor": bins["hyprctl"] or bins["axctl"],
        "atspi": bool(atspi_ok),
        "noscreenshare": bool(native.get("noscreenshare")),
        "locked": bool(native.get("locked")),
        "screens": native.get("screens") or [],
        "focused_window": native.get("focused_window"),
        "windows": native.get("windows") or [],
        "coordinate_space": "per-monitor grim physical mapped with that output's scale",
        "binaries": bins,
    }
    blockers = []
    if native.get("locked"):
        blockers.append("session is locked")
    if not bins["grim"]:
        blockers.append("grim is missing")
    if not bins["wtype"] and not bins["ydotool"]:
        blockers.append("no keyboard backend (wtype/ydotool)")
    report["can_screenshot"] = bins["grim"] and not native.get("locked")
    report["can_type"] = bins["wtype"] or bins["ydotool"]
    report["can_click"] = bins["ydotool"] and (ydo_sock or uinput_writable())
    report["recommended_next_step"] = (
        blockers[0]
        if blockers
        else (
            "start ydotoold"
            if bins["ydotool"] and not ydo_sock and not report["can_click"]
            else "call use_computer action=snapshot"
        )
    )
    report["blockers"] = blockers
    return report
