"""Pointer and keyboard injection. Aim with compositor movecursor, never ydotool --absolute."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time

from .doctor import ydotool_socket_path

INPUT_LOCK = threading.Lock()
MOVE_SETTLE = 0.03
CLICK_HOLD = 0.035
FOCUS_SETTLE = 0.12
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


def movecursor(x, y):
    hypr = shutil.which("hyprctl")
    if hypr:
        result = _run([hypr, "dispatch", "movecursor", str(int(x)), str(int(y))])
        if result.returncode == 0 and (result.stdout or b"").strip() in (b"ok", b""):
            time.sleep(MOVE_SETTLE)
            return True
    axctl = shutil.which("axctl")
    if axctl:
        result = _run([axctl, "system", "execute", "movecursor %s %s" % (int(x), int(y))])
        time.sleep(MOVE_SETTLE)
        return result.returncode == 0
    return False


def _ydotool_env():
    return {"YDOTOOL_SOCKET": ydotool_socket_path()}


def _ydotool(args, timeout=10):
    exe = shutil.which("ydotool")
    if not exe:
        raise RuntimeError("ydotool is not installed")
    result = _run([exe] + list(args), timeout=timeout, env=_ydotool_env())
    if result.returncode != 0:
        err = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(err or "ydotool failed")
    return True


def click(button="left", count=1):
    code = YDOTOOL_CLICK.get(str(button or "left").lower())
    if not code:
        raise RuntimeError("unsupported mouse button: %s" % button)
    repeats = max(1, min(10, int(count or 1)))
    with INPUT_LOCK:
        _ydotool(["click", "--repeat", str(repeats), code])


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
        if not movecursor(sx, sy):
            raise RuntimeError("movecursor failed")
        _held.append(up)
        try:
            _ydotool(["click", down])
            time.sleep(CLICK_HOLD)
            if not movecursor(ex, ey):
                raise RuntimeError("movecursor failed")
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
    wtype = shutil.which("wtype")
    with INPUT_LOCK:
        if wtype:
            result = _run([wtype, "-"], timeout=max(10, 4 + len(text) / 20), stdin_data=text.encode("utf-8"))
            if result.returncode == 0:
                return True
            raise RuntimeError((result.stderr or b"").decode("utf-8", "replace") or "wtype failed")
        timeout = max(10, 10 + len(text) / 20)
        exe = shutil.which("ydotool")
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
    hypr = shutil.which("hyprctl")
    if hypr:
        modmask = ",".join(HYPR_MOD[m] for m in mods if m in HYPR_MOD)
        target = address or "activewindow"
        if not str(target).startswith("address:") and target != "activewindow":
            target = "address:%s" % target
        args = [hypr, "dispatch", "sendshortcut"]
        chord = "%s,%s,%s" % (modmask, key, target) if modmask else "%s,%s" % (key, target)
        # hyprctl sendshortcut: [modmask,]key,window
        if modmask:
            result = _run([hypr, "dispatch", "sendshortcut", modmask, key, target])
        else:
            result = _run([hypr, "dispatch", "sendshortcut", key, target])
        if result.returncode == 0 and b"Invalid" not in (result.stdout or b"") + (result.stderr or b""):
            return True
    wtype = shutil.which("wtype")
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
        ydo = shutil.which("ydotool")
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
