"""Readiness probes for native computer use."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path


HUD_NAMESPACE = "ambxst+:computer-use"


def _which(name):
    return shutil.which(name) or ""


def ydotool_socket_candidates(preferred=None):
    seen = []
    for path in (
        preferred,
        os.environ.get("YDOTOOL_SOCKET"),
        str(Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / ".ydotool_socket"),
        "/tmp/.ydotool_socket",
    ):
        text = str(path or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def ydotool_socket_connects(path):
    if not path or not os.path.exists(path):
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


def find_ydotool_socket(preferred=None):
    for path in ydotool_socket_candidates(preferred):
        if ydotool_socket_connects(path):
            return path
    return ""


def ydotool_socket_path(preferred=None):
    found = find_ydotool_socket(preferred)
    if found:
        os.environ["YDOTOOL_SOCKET"] = found
        return found
    return ydotool_socket_candidates(preferred)[0]


def ydotool_socket_ok(preferred=None):
    return bool(find_ydotool_socket(preferred))


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


def parse_layers_noscreenshare(data, namespace=HUD_NAMESPACE):
    want = str(namespace or "")
    found_ns = False

    def walk(node):
        nonlocal found_ns
        hit = False
        if isinstance(node, dict):
            ns = str(node.get("namespace") or "")
            if ns == want:
                found_ns = True
                if node.get("noscreenshare") or node.get("no_screen_share"):
                    return True
            for value in node.values():
                if walk(value):
                    hit = True
        elif isinstance(node, list):
            for item in node:
                if walk(item):
                    hit = True
        return hit

    return walk(data), found_ns


def layer_noscreenshare(namespace=HUD_NAMESPACE):
    hypr = _which("hyprctl")
    if not hypr:
        return False
    try:
        out = subprocess.check_output([hypr, "layers", "-j"], stderr=subprocess.DEVNULL, timeout=4)
        data = json.loads(out.decode("utf-8", "replace") or "{}")
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return False
    flagged, _found = parse_layers_noscreenshare(data, namespace)
    return bool(flagged)


def doctor_report(native=None, atspi_ok=None):
    bins = probe_binaries()
    native = native or {}
    preferred = native.get("ydotool_socket") or ""
    socket_path = find_ydotool_socket(preferred)
    ydo_sock = bool(socket_path)
    noscreenshare = layer_noscreenshare()
    report = {
        "grim": bins["grim"],
        "wtype": bins["wtype"],
        "ydotool": bins["ydotool"],
        "ydotool_socket": ydo_sock,
        "ydotool_socket_path": socket_path,
        "uinput": uinput_writable(),
        "sendshortcut": bins["hyprctl"],
        "movecursor": bins["hyprctl"] or bins["axctl"],
        "atspi": bool(atspi_ok),
        "noscreenshare": noscreenshare,
        "hide_for_capture": True,
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
    report["can_click"] = bool(bins["ydotool"] and ydo_sock)
    report["recommended_next_step"] = (
        blockers[0]
        if blockers
        else (
            "start ydotoold"
            if bins["ydotool"] and not ydo_sock
            else "call use_computer action=snapshot"
        )
    )
    report["blockers"] = blockers
    if socket_path:
        os.environ["YDOTOOL_SOCKET"] = socket_path
    return report
