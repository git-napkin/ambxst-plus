"""Pointer and keyboard injection. Aim with compositor movecursor, never ydotool --absolute."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time

from .doctor import find_ydotool_socket, ydotool_socket_path

INPUT_LOCK = threading.Lock()
_WHICH = {}


def _which(name):
    cached = _WHICH.get(name)
    if cached is not None:
        return cached or None
    found = shutil.which(name) or ""
    _WHICH[name] = found
    return found or None


MOVE_SETTLE = 0.03
CLICK_HOLD = 0.035
FOCUS_SETTLE = 0.05
MOVE_MIN_MS = 80
MOVE_MAX_MS = 350
MOVE_STEPS_MIN = 4
MOVE_STEPS_MAX = 8
YDOTOOL_CLICK = {
    "left": "0xC0",
    "primary": "0xC0",
    "right": "0xC1",
    "middle": "0xC2",
    "side": "0xC3",
    "extra": "0xC4",
    "forward": "0xC5",
    "back": "0xC6",
}
YDOTOOL_CLICK_NAME = {
    "left": "BTN_LEFT",
    "primary": "BTN_LEFT",
    "right": "BTN_RIGHT",
    "middle": "BTN_MIDDLE",
    "side": "BTN_SIDE",
    "extra": "BTN_EXTRA",
    "forward": "BTN_FORWARD",
    "back": "BTN_BACK",
}
YDOTOOL_DOWN = {
    "left": "0x40",
    "primary": "0x40",
    "right": "0x41",
    "middle": "0x42",
}
YDOTOOL_UP = {
    "left": "0x80",
    "primary": "0x80",
    "right": "0x81",
    "middle": "0x82",
}

NAMED_KEYS = {
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
}

MOD_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "meta": "super",
    "super": "super",
    "cmd": "super",
    "command": "super",
}

HYPR_MOD = {
    "ctrl": "CONTROL",
    "alt": "ALT",
    "shift": "SHIFT",
    "super": "SUPER",
}

_held = []
_click_form = None


def _run(argv, timeout=10, stdin_data=None, env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        argv,
        input=stdin_data,
        capture_output=True,
        timeout=timeout,
        env=merged,
        check=False,
    )


def _decode_proc(result):
    blob = (result.stderr or b"") + b"\n" + (result.stdout or b"")
    return blob.decode("utf-8", "replace").strip()


def _hypr_dispatch_ok(result):
    if result.returncode != 0:
        return False
    return (result.stdout or b"").strip() in (b"ok", b"")


def _parse_cursor_text(text):
    raw = str(text or "").strip()
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
            return int(obj.get("x") or 0), int(obj.get("y") or 0)
        except (TypeError, ValueError):
            pass
    parts = raw.replace(" ", "").split(",")
    if len(parts) >= 2:
        try:
            return int(float(parts[0])), int(float(parts[1]))
        except (TypeError, ValueError):
            return None
    return None


def cursor_position():
    axctl = _which("axctl")
    if axctl:
        result = _run([axctl, "system", "get-cursor-position"], timeout=4)
        parsed = _parse_cursor_text((result.stdout or b"").decode("utf-8", "replace"))
        if parsed:
            return parsed
    hypr = _which("hyprctl")
    if hypr:
        result = _run([hypr, "cursorpos"], timeout=4)
        parsed = _parse_cursor_text((result.stdout or b"").decode("utf-8", "replace"))
        if parsed:
            return parsed
    return None


def _ease_in_out(t):
    t = max(0.0, min(1.0, float(t)))
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 2) / 2.0


def _dispatch_move(x, y):
    ix, iy = int(round(x)), int(round(y))
    errors = []
    hypr = _which("hyprctl")
    if hypr:
        lua = "hl.dsp.cursor.move({ x = %d, y = %d })" % (ix, iy)
        result = _run([hypr, "dispatch", lua])
        if _hypr_dispatch_ok(result):
            return True
        errors.append("hyprctl lua: " + (_decode_proc(result) or ("exit %s" % result.returncode)))
        result = _run([hypr, "dispatch", "movecursor", str(ix), str(iy)])
        if _hypr_dispatch_ok(result):
            return True
        errors.append("hyprctl movecursor: " + (_decode_proc(result) or ("exit %s" % result.returncode)))
    axctl = _which("axctl")
    if axctl:
        result = _run([axctl, "system", "move-cursor", str(ix), str(iy)])
        blob = (result.stderr or b"") + (result.stdout or b"")
        if result.returncode == 0 and b"Error" not in blob and b"method not found" not in blob.lower():
            return True
        errors.append("axctl: " + (_decode_proc(result) or ("exit %s" % result.returncode)))
    raise RuntimeError("movecursor failed: " + ("; ".join(errors) or "no hyprctl/axctl"))


def movecursor(x, y):
    ix, iy = int(round(x)), int(round(y))
    start = cursor_position()
    if start:
        sx, sy = start
        dist = ((ix - sx) ** 2 + (iy - sy) ** 2) ** 0.5
        if dist >= 2:
            duration = min(MOVE_MAX_MS, max(MOVE_MIN_MS, dist * 0.35)) / 1000.0
            steps = min(MOVE_STEPS_MAX, max(MOVE_STEPS_MIN, int(dist / 90) + 8))
            dt = duration / float(steps)
            for i in range(1, steps + 1):
                t = _ease_in_out(i / float(steps))
                _dispatch_move(sx + (ix - sx) * t, sy + (iy - sy) * t)
                if i < steps:
                    time.sleep(dt)
            return True
    _dispatch_move(ix, iy)
    time.sleep(MOVE_SETTLE)
    return True


def _ydotool_env():
    path = find_ydotool_socket() or ydotool_socket_path()
    return {"YDOTOOL_SOCKET": path}


def _ydotool(args, timeout=10):
    exe = _which("ydotool")
    if not exe:
        raise RuntimeError("ydotool is not installed")
    sock = find_ydotool_socket()
    if not sock:
        raise RuntimeError("ydotool socket is not connected (is ydotoold running?)")
    result = _run([exe] + list(args), timeout=timeout, env={"YDOTOOL_SOCKET": sock})
    if result.returncode != 0:
        err = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(err or "ydotool failed")
    return True


def _click_code(button):
    global _click_form
    key = str(button or "left").lower()
    hex_code = YDOTOOL_CLICK.get(key)
    name_code = YDOTOOL_CLICK_NAME.get(key)
    if not hex_code and not name_code:
        raise RuntimeError("unsupported mouse button: %s" % button)
    if _click_form is None:
        exe = _which("ydotool")
        help_text = ""
        if exe:
            result = _run([exe, "click", "--help"], timeout=4)
            help_text = ((result.stdout or b"") + (result.stderr or b"")).decode("utf-8", "replace")
        if "BTN_LEFT" in help_text and "0xC0" not in help_text:
            _click_form = "name"
        else:
            _click_form = "hex"
    if _click_form == "name":
        return name_code or hex_code
    return hex_code or name_code


def click(button="left", count=1):
    global _click_form
    code = _click_code(button)
    repeats = max(1, min(10, int(count or 1)))
    with INPUT_LOCK:
        try:
            _ydotool(["click", "--repeat", str(repeats), code])
        except RuntimeError as exc:
            alt = YDOTOOL_CLICK_NAME.get(str(button or "left").lower()) if _click_form != "name" else YDOTOOL_CLICK.get(str(button or "left").lower())
            if alt and alt != code:
                _click_form = "name" if _click_form != "name" else "hex"
                _ydotool(["click", "--repeat", str(repeats), alt])
                return
            raise RuntimeError("click failed: %s" % exc) from exc


def scroll(direction="down", pages=1):
    ticks = max(1, int(round(abs(float(pages or 1)) * 5)))
    direction = str(direction or "down").lower()
    dx, dy = 0, 0
    if direction == "up":
        dy = ticks
    elif direction == "down":
        dy = -ticks
    elif direction == "left":
        dx = ticks
    elif direction == "right":
        dx = -ticks
    else:
        raise RuntimeError("unsupported scroll direction: %s" % direction)
    with INPUT_LOCK:
        _ydotool(["mousemove", "--wheel", "--", str(dx), str(dy)])


def drag(start, end, button="left"):
    down = YDOTOOL_DOWN.get(str(button or "left").lower())
    up = YDOTOOL_UP.get(str(button or "left").lower())
    if not down or not up:
        raise RuntimeError("drag only supports left/right/middle")
    sx, sy = start
    ex, ey = end
    with INPUT_LOCK:
        movecursor(sx, sy)
        _held.append(up)
        try:
            _ydotool(["click", down])
            time.sleep(CLICK_HOLD)
            movecursor(ex, ey)
            time.sleep(CLICK_HOLD)
            _ydotool(["click", up])
        finally:
            if _held and _held[-1] == up:
                _held.pop()


def release_held():
    with INPUT_LOCK:
        while _held:
            code = _held.pop()
            try:
                _ydotool(["click", code])
            except Exception:
                pass


def type_text(text):
    text = str(text or "")
    if not text:
        return True
    wtype = _which("wtype")
    with INPUT_LOCK:
        if wtype:
            result = _run([wtype, "-"], timeout=max(10, 4 + len(text) / 20), stdin_data=text.encode("utf-8"))
            if result.returncode == 0:
                return True
            raise RuntimeError((result.stderr or b"").decode("utf-8", "replace") or "wtype failed")
        timeout = max(10, 10 + len(text) / 20)
        exe = _which("ydotool")
        if not exe:
            raise RuntimeError("wtype and ydotool are missing")
        result = _run(
            [exe, "type", "--file", "-"],
            timeout=timeout,
            stdin_data=text.encode("utf-8"),
            env=_ydotool_env(),
        )
        if result.returncode != 0:
            raise RuntimeError("ydotool type failed")
    return True


def parse_chord(spec):
    raw = str(spec or "").strip()
    if not raw:
        raise RuntimeError("empty key")
    parts = [p for p in raw.replace("-", "+").replace(" ", "+").split("+") if p]
    mods = []
    key = None
    for part in parts:
        low = part.lower()
        if low in MOD_ALIASES:
            mods.append(MOD_ALIASES[low])
            continue
        if key is not None:
            raise RuntimeError("unsupported key grammar: %s" % spec)
        if low in NAMED_KEYS:
            key = NAMED_KEYS[low]
        elif len(part) == 1:
            key = part
        elif low.startswith("f") and low[1:].isdigit():
            key = part.upper()
        else:
            raise RuntimeError("unsupported key: %s" % part)
    if key is None:
        raise RuntimeError("unsupported key grammar: %s" % spec)
    return mods, key


def press_key(spec, address=""):
    mods, key = parse_chord(spec)
    modmask = ",".join(HYPR_MOD[m] for m in mods if m in HYPR_MOD)
    target = address or "activewindow"
    if not str(target).startswith("address:") and target != "activewindow":
        target = "address:%s" % target
    hypr = _which("hyprctl")
    if hypr:
        if modmask:
            result = _run([hypr, "dispatch", "sendshortcut", modmask, key, target])
        else:
            result = _run([hypr, "dispatch", "sendshortcut", key, target])
        if result.returncode == 0 and b"Invalid" not in (result.stdout or b"") + (result.stderr or b""):
            return True
    axctl = _which("axctl")
    if axctl:
        result = _run([axctl, "system", "send-shortcut", modmask, key, target])
        if result.returncode == 0 and b"Error" not in (result.stderr or b"") + (result.stdout or b""):
            return True
    wtype = _which("wtype")
    with INPUT_LOCK:
        if wtype:
            argv = [wtype]
            for mod in mods:
                argv.extend(["-M", mod])
            argv.extend(["-k", key])
            for mod in reversed(mods):
                argv.extend(["-m", mod])
            result = _run(argv, timeout=8)
            if result.returncode == 0:
                return True
        ydo = _which("ydotool")
        if ydo:
            chord = []
            for mod in mods:
                chord.append(mod.upper() if mod != "ctrl" else "LEFTCTRL")
            chord.append(key.upper() if len(key) > 1 else key)
            result = _run([ydo, "key"] + chord, timeout=8, env=_ydotool_env())
            if result.returncode == 0:
                return True
        raise RuntimeError("could not send key %s" % spec)
    return True
